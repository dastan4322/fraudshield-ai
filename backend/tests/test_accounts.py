import secrets
import time
from io import BytesIO
from fastapi.testclient import TestClient
from sqlalchemy import select
from pypdf import PdfReader
from app.main import app, models
from app.database import DB, Session, User
from app.accounts import digest

def register(client):
    address=secrets.token_hex(8)+"@example.test"
    res=client.post("/api/auth/register",json={"email":address,"password":"Long-test-password-42!"})
    assert res.status_code==201,res.text
    return address,{"X-CSRF-Token":res.json()["csrf_token"]}

def test_registration_login_logout_and_csrf():
    with TestClient(app) as client:
        address,headers=register(client)
        assert client.get("/api/auth/me").json()["email"]==address
        assert client.post("/api/auth/logout").status_code==403
        assert client.post("/api/auth/logout",headers=headers).status_code==200
        assert client.get("/api/auth/me").status_code==401
        assert client.post("/api/auth/login",json={"email":address,"password":"incorrect-password"}).status_code==401
        login=client.post("/api/auth/login",json={"email":address,"password":"Long-test-password-42!"})
        assert login.status_code==200
        assert "HttpOnly" in login.headers["set-cookie"]
        with DB() as db:
            user=db.scalar(select(User).where(User.email==address))
            assert user.password.startswith("$argon2")
            assert db.get(Session,digest(client.cookies.get("fraudshield_session")))

def test_resource_ownership_and_account_cascade():
    with TestClient(app) as alice,TestClient(app) as bob:
        _,ha=register(alice);_,hb=register(bob)
        result=alice.post("/api/workspace/resources",headers=ha,json={"kind":"dataset","name":"Fixture only","payload":{"records":[{"amount":2}]}})
        key=result.json()["id"]
        assert bob.get("/api/workspace/resources/"+key).status_code==404
        assert bob.delete("/api/workspace/resources/"+key,headers=hb).status_code==404
        assert alice.get("/api/workspace/resources/"+key).json()["payload"]["records"][0]["amount"]==2
        assert alice.delete("/api/auth/account",headers=ha).status_code==200
        assert alice.get("/api/auth/me").status_code==401
        assert bob.get("/api/workspace/resources").json()==[]

def test_reset_delivery_single_use_and_session_revocation(monkeypatch):
    delivered=[]
    monkeypatch.setattr("app.accounts.deliver_reset",lambda address,token:delivered.append(token))
    with TestClient(app) as client:
        address,headers=register(client)
        response=client.post("/api/auth/forgot-password",headers=headers,json={"email":address})
        assert response.status_code==200
        assert delivered
        token=delivered[0]
        body={"token":token,"password":"Changed-test-password-42!"}
        assert client.post("/api/auth/reset-password",headers=headers,json=body).status_code==200
        assert client.get("/api/auth/me").status_code==401
        client.cookies.clear()
        assert client.post("/api/auth/reset-password",json=body).status_code==400
        assert client.post("/api/auth/login",json={"email":address,"password":body["password"]}).status_code==200

def test_user_training_persists_and_is_private():
    with TestClient(app) as alice,TestClient(app) as bob:
        _,ha=register(alice);_,hb=register(bob)
        rows=alice.get("/api/demo/transactions").json()["records"]
        res=alice.post("/api/models/train",headers=ha,json={"records":rows,"target":"is_fraud"})
        assert res.status_code==202,res.text
        key=res.json()["job_id"]
        for _ in range(200):
            state=alice.get("/api/jobs/"+key,headers=ha).json()
            if state["status"] in {"complete","failed"}:
                break
            time.sleep(.05)
        assert state["status"]=="complete",state
        assert key not in models # persistent DB artifact, not shared in-memory model registry
        assert bob.get("/api/jobs/"+key).status_code==404
        assert bob.post("/api/predict",headers=hb,json={"model_id":key,"records":rows[:1]}).status_code==404
        assert alice.post("/api/predict",headers=ha,json={"model_id":key,"records":rows[:1]}).status_code==200
        assert any(m["id"]==key for m in alice.get("/api/models").json())
        assert alice.delete("/api/workspace",headers=ha).status_code==200
        assert alice.get("/api/models/"+key+"/metrics").status_code==404

def test_pdf_and_shap():
    import numpy as np
    with TestClient(app) as client:
        rows=client.get("/api/demo/transactions").json()["records"][:3]
        payload={"records":rows}
        explanation=client.post("/api/explain",json=payload)
        assert explanation.status_code==200,explanation.text
        data=explanation.json()
        assert data["method"]=="Permutation SHAP"
        np.testing.assert_allclose(np.array(data["base_values"])+np.sum(data["values"],axis=1),data["predictions"],atol=1e-6)
        assert len(data["global_importance"])==4
        result=client.post("/api/reports",json={**payload,"format":"pdf"})
        assert result.headers["content-type"]=="application/pdf"
        text="".join(p.extract_text() for p in PdfReader(BytesIO(result.content)).pages)
        assert "FraudShield" in text and "threshold" in text

def test_unlabeled_anomaly_analysis():
    with TestClient(app) as client:
        csv="amount,hour\n"+"\n".join(f"{i+1},{i%24}" for i in range(30))
        res=client.post("/api/datasets/analyze",files={"file":("test.csv",csv)})
        assert res.status_code==200,res.text
        assert len(res.json()["anomaly_percentiles"])==30
