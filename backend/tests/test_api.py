import time
import pytest
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_end_to_end(client):
    assert client.get("/api/health").json()["models_ready"]
    records=client.get("/api/demo/transactions").json()["records"][:10]
    body={"records":records,"model_id":"demo-logistic","threshold":.3}
    response=client.post("/api/predict/batch",json=body)
    assert response.status_code==200
    assert len(response.json()["records"])==10
    assert client.post("/api/explain",json=body).json()["contributions"]
    assert "risk_score" in client.post("/api/reports",json=body).text
    assert "Investigation report" in client.post("/api/reports",json={**body,"format":"html"}).text
    assert client.post("/api/predict",json={"records":[{"unknown":2}]}).status_code==422
    assert client.post("/api/models/train",json={"records":records*10,"target":"is_fraud"}).status_code==401

def test_upload(client):
    res=client.post("/api/datasets/analyze",files={"file":("test.csv",b"amount,hour\n2,3\n4,5")})
    assert res.status_code==200
    assert res.json()["rows"]==2
    assert client.post("/api/datasets/validate",files={"file":("bad.exe",b"a")}).status_code==422
    assert client.post("/api/datasets/analyze",files={"file":("big.csv",b"a"*2_000_001)}).status_code==413

def test_custom_training(client,monkeypatch):
    monkeypatch.setenv("WORKSPACE_TOKEN","test-only-token")
    records=client.get("/api/demo/transactions").json()["records"]
    headers={"X-Workspace-Token":"test-only-token"}
    response=client.post("/api/models/train",json={"records":records,"target":"is_fraud"},headers=headers)
    assert response.status_code==202
    key=response.json()["job_id"]
    for _ in range(100):
        state=client.get("/api/jobs/"+key,headers=headers).json()
        if state["status"] in {"complete","failed"}:
            break
        time.sleep(.1)
    assert state["status"]=="complete",state
    assert client.get("/api/models/"+key+"/metrics").status_code==401
    assert client.post("/api/predict",headers=headers,json={"model_id":key,"records":records[:2]}).status_code==200
    assert client.delete("/api/workspace",headers=headers).json()["deleted"]
    assert client.get("/api/models/"+key+"/metrics",headers=headers).status_code==404
