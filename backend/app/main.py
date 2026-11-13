import asyncio
import csv
import io
import json
import logging
import os
import secrets
import time
import threading
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from html import escape

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text as sql_text
from .database import initialize, DB, Artifact, Resource
from .accounts import router as accounts_router, current, require_csrf
from .ml import synthetic, train, predict, explain, validate

models = {}
jobs = {}
training_lock=threading.Lock()
executor = ThreadPoolExecutor(max_workers=1)
limits = defaultdict(deque)
log = logging.getLogger("fraudshield")

@asynccontextmanager
async def lifespan(app):
    initialize()
    data = synthetic()
    for algorithm in ["logistic", "forest", "xgboost"]:
        bundle = await asyncio.to_thread(train, data, "is_fraud", algorithm)
        bundle["source"] = "synthetic demonstration"
        models["demo-" + algorithm] = bundle
    artifact = os.getenv("MODEL_ARTIFACT")
    if artifact:
        import joblib
        # Administrators only: never accept model paths from HTTP clients.
        models["local-trained"] = joblib.load(artifact)
    yield

app = FastAPI(title="FraudShield AI", version="1.0.0", lifespan=lifespan)
app.include_router(accounts_router)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
                   allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type", "X-Workspace-Token", "X-CSRF-Token"], allow_credentials=True)

@app.middleware("http")
async def guard(request: Request, call_next):
    now = time.monotonic()
    key = request.client.host if request.client else "unknown"
    is_auth=request.url.path.startswith("/api/auth/") and request.method=="POST"
    queue = limits[key+(":auth" if is_auth else "")]
    while queue and queue[0] < now-60:
        queue.popleft()
    if len(queue) >= (10 if is_auth else 120):
        return Response('{"detail":"Rate limit exceeded"}', 429, media_type="application/json")
    queue.append(now)
    if len(limits) > 10000:
        for host in list(limits):
            if not limits[host] or limits[host][-1] < now-60:
                del limits[host]
    length = request.headers.get("content-length")
    if length and (not length.isdecimal()):
        return Response('{"detail":"Invalid Content-Length"}',400,media_type="application/json")
    if length and int(length) > 2_000_000:
        return Response('{"detail":"Upload limit is 2 MB"}', 413, media_type="application/json")
    if request.method in {"POST", "PUT", "PATCH"}:
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 2_000_000:
                return Response('{"detail":"Request limit is 2 MB"}', 413, media_type="application/json")
            chunks.append(chunk)
        request._body = b"".join(chunks)
    try:
        require_csrf(request)
    except HTTPException as exc:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail":exc.detail},status_code=exc.status_code)
    response = await call_next(request)
    log.info(json.dumps({"method":request.method,"path":request.url.path,"status":response.status_code}))
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response

@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503,content={"detail":"Workspace storage is temporarily unavailable."})

@app.exception_handler(ValueError)
async def invalid(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422, content={"detail": str(exc)})

def owner(request):
    identity=current(request,required=False)
    if identity:
        return identity
    configured = os.getenv("WORKSPACE_TOKEN")
    supplied = request.headers.get("x-workspace-token", "")
    if not configured or not secrets.compare_digest(configured, supplied):
        raise HTTPException(401, "Private training requires the server's WORKSPACE_TOKEN.")
    return "private"

def get_model(model_id, request):
    if model_id.startswith("demo-") and model_id in models:
        return models[model_id]
    identity=owner(request)
    if model_id=="local-trained" and identity=="private" and model_id in models:
        return models[model_id]
    if identity=="private":
        if model_id in models and model_owners.get(model_id)=="private":
            return models[model_id]
    else:
        with DB() as db:
            artifact=db.get(Artifact,model_id)
            if artifact and artifact.user_id==identity:
                import joblib
                return joblib.load(io.BytesIO(artifact.data))
    raise HTTPException(404,"Model not found")

model_owners={}

def metadata(key, bundle):
    return {"id": key, **{k:v for k,v in bundle.items() if k not in {"model", "baseline", "background"}}}

class Prediction(BaseModel):
    model_id: str = "demo-logistic"
    records: list[dict[str, float | str]] = Field(min_length=1, max_length=10000)
    threshold: float = Field(default=.5, ge=0, le=1)

class Training(BaseModel):
    records: list[dict[str, float | str | None]] = Field(min_length=100, max_length=10000)
    target: str
    algorithm: str = "logistic"
    features: list[str] | None = None
    positive_class: str = "1"
    review_cost: float = Field(default=1, gt=0, le=100000)
    missed_cost: float = Field(default=25, gt=0, le=100000)

class Report(Prediction):
    format: str = "csv"
    review_statuses: dict[str,str] = Field(default_factory=dict,max_length=10000)

def result(body, request):
    bundle = get_model(body.model_id, request)
    scores = predict(bundle, pd.DataFrame(body.records))
    return [{"transaction_id": str(i+1), **record, "risk_score": float(score),
             "risk_category": "high" if score >= body.threshold else "medium" if score >= body.threshold/2 else "low",
             "prediction": int(score >= body.threshold)} for i,(record,score) in enumerate(zip(body.records,scores))]

@app.get("/api/health")
def health():
    with DB() as db:
        db.execute(sql_text("SELECT 1"))
    return {"status":"ok", "models_ready": bool(models), "database":"ok"}

@app.get("/api/models")
def list_models(request: Request):
    entries=[metadata(k,v) for k,v in models.items() if k.startswith("demo-")]
    try:
        identity=owner(request)
    except HTTPException:
        return entries
    if identity=="private":
        entries.extend(metadata(k,v) for k,v in models.items() if model_owners.get(k)=="private" or k=="local-trained")
    else:
        from sqlalchemy import select
        import joblib
        with DB() as db:
            entries.extend(metadata(a.id,joblib.load(io.BytesIO(a.data))) for a in db.scalars(select(Artifact).where(Artifact.user_id==identity)))
    return entries

@app.get("/api/demo/transactions")
def demo():
    return {"source": "Synthetic data; not Kaggle or real financial records.", "records": synthetic().head(200).to_dict("records")}

@app.get("/api/models/{model_id}/metrics")
def model_metrics(model_id: str, request: Request):
    return metadata(model_id, get_model(model_id, request))

async def read_csv(file):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise ValueError("Upload a UTF-8 CSV file.")
    data = await file.read(2_000_001)
    if len(data)>2_000_000:
        raise HTTPException(413, "Upload limit is 2 MB")
    try:
        text = data.decode("utf-8-sig")
        headers = next(csv.reader(io.StringIO(text)))
        if len(headers) != len(set(headers)):
            raise ValueError("Duplicate column names are unsupported.")
        frame = pd.read_csv(io.StringIO(text))
    except (UnicodeError, pd.errors.ParserError, StopIteration, pd.errors.EmptyDataError):
        raise ValueError("Invalid UTF-8 CSV.")
    validate(frame)
    return frame

@app.post("/api/datasets/validate")
@app.post("/api/datasets/analyze")
async def profile(file: UploadFile = File(...)):
    frame = await read_csv(file)
    numeric = frame.select_dtypes(include="number")
    anomalies = None
    if len(numeric.columns) and len(frame)>5 and not numeric.isna().any().any():
        values = IsolationForest(random_state=42, n_jobs=1).fit(numeric).score_samples(numeric)
        anomalies = pd.Series(-values).rank(pct=True).tolist()
    return {"rows":len(frame), "columns":list(frame), "dtypes":{k:str(v) for k,v in frame.dtypes.items()},
            "missing":{k:int(v) for k,v in frame.isna().sum().items()}, "duplicates":int(frame.duplicated().sum()),
            "records":json.loads(frame.to_json(orient="records")), "anomaly_percentiles":anomalies,
            "warning":"Anomaly percentiles are not fraud probabilities. Remove identifiers and leakage-prone features before training."}

@app.post("/api/predict")
@app.post("/api/predict/batch")
def inference(body: Prediction, request: Request):
    return {"records":result(body, request), "model_id":body.model_id, "threshold":body.threshold}

@app.post("/api/explain")
def explanation(body: Prediction, request: Request):
    bundle = get_model(body.model_id, request)
    from .explanations import shap_explain
    return shap_explain(bundle, pd.DataFrame(body.records[:20]))

@app.post("/api/models/train", status_code=202)
def training(body: Training, request: Request):
    identity=owner(request)
    if any(j["status"] in {"queued", "running"} for j in jobs.values()):
        raise HTTPException(409, "One training job is already active.")
    if identity!="private":
        from sqlalchemy import select,func
        with DB() as db:
            count=db.scalar(select(func.count()).select_from(Artifact).where(Artifact.user_id==identity))
            if count>=20:
                raise HTTPException(409,"Model limit: delete an older model before training.")
    frame = pd.DataFrame(body.records)
    validate(frame)
    if body.target not in frame:
        raise ValueError("Target column is missing.")
    if frame[body.target].isna().any() or frame[body.target].nunique()!=2:
        raise ValueError("Target must have exactly two non-missing classes.")
    labels = frame[body.target].map(lambda v: str(int(v)) if isinstance(v, (int, float)) and float(v).is_integer() else str(v))
    if body.positive_class not in set(labels):
        raise ValueError("Positive class was not found.")
    frame[body.target] = (labels == body.positive_class).astype(int)
    if body.features is not None:
        if not body.features:
            raise ValueError("Select at least one feature.")
        if body.target in body.features or set(body.features)-set(frame):
            raise ValueError("Features must exist and exclude the target.")
        frame = frame[body.features + [body.target]]
    identifier = secrets.token_hex(12)
    with training_lock:
        if any(j["status"] in {"queued","running"} for j in jobs.values()):
            raise HTTPException(409,"One training job is already active.")
        if len(jobs)>=100:
            raise HTTPException(409,"Job history limit reached. Clear your workspace.")
        jobs[identifier] = {"status":"queued","owner":identity}
    def run():
        jobs[identifier] = {"status":"running","owner":identity}
        try:
            bundle = train(frame, body.target, body.algorithm, body.review_cost, body.missed_cost)
            if identity=="private":
                models[identifier] = bundle
                model_owners[identifier]=identity
            else:
                import joblib
                buffer=io.BytesIO();joblib.dump(bundle,buffer)
                with DB() as db:
                    from .database import User
                    if db.get(User,identity) is None:
                        raise ValueError("Account deleted during training.")
                    db.add(Artifact(id=identifier,user_id=identity,data=buffer.getvalue()));db.commit()
            jobs[identifier] = {"status":"complete", "model_id":identifier,"owner":identity}
        except Exception as exc:
            jobs[identifier] = {"status":"failed", "detail":"Training failed. Check feature types, class counts and input values.","owner":identity}
    executor.submit(run)
    return {"job_id":identifier}

@app.get("/api/jobs/{job_id}")
def job(job_id: str, request: Request):
    identity=owner(request)
    if job_id not in jobs or jobs[job_id].get("owner")!=identity:
        raise HTTPException(404, "Job not found")
    return {k:v for k,v in jobs[job_id].items() if k!="owner"}

@app.delete("/api/workspace")
def delete(request: Request):
    identity=owner(request)
    if any(j["status"] in {"queued","running"} and j.get("owner")==identity for j in jobs.values()):
        raise HTTPException(409,"Wait for active training to finish before deleting.")
    from sqlalchemy import delete as sql_delete
    if identity!="private":
        with DB() as db:
            db.execute(sql_delete(Artifact).where(Artifact.user_id==identity))
            db.execute(sql_delete(Resource).where(Resource.user_id==identity));db.commit()
    for key in list(models):
        if model_owners.get(key)==identity:
            del models[key];model_owners.pop(key,None)
    for key in list(jobs):
        if jobs[key].get("owner")==identity:
            del jobs[key]
    return {"deleted":True}

@app.post("/api/reports")
def report(body: Report, request: Request):
    rows = result(body, request)
    for row in rows:
        row["review_status"]=body.review_statuses.get(row["transaction_id"],"unreviewed")
    if body.format=="pdf":
        from .pdf import make_pdf
        return Response(make_pdf(rows,get_model(body.model_id,request),body.model_id,body.threshold),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=report.pdf"})
    if body.format=="html":
        bundle=get_model(body.model_id,request)
        summary = {"model":body.model_id, "version":bundle["version"], "source":bundle["source"], "threshold":body.threshold, "rows":len(rows), "flagged":sum(r["prediction"] for r in rows)}
        content = "<!doctype html><html><meta charset='utf-8'><title>FraudShield report</title><h1>Investigation report</h1><pre>"+escape(json.dumps(summary, indent=2))+"</pre><p>Decision support only. Not proof of fraud. Synthetic demo models are not validated on real financial data.</p></html>"
        bars="".join(f'<p>{category}: {sum(r["risk_category"]==category for r in rows)} <meter min="0" max="{len(rows)}" value="{sum(r["risk_category"]==category for r in rows)}"></meter></p>' for category in ["low","medium","high"])
        content=content.replace("</html>","<h2>Risk distribution</h2>"+bars+"<h2>Held-out training metrics</h2><pre>"+escape(json.dumps(bundle["metrics"],indent=2))+"</pre><p>These metrics describe the model evaluation split, not the current upload. Investigate flagged records and verify evidence manually.</p></html>")
        return Response(content, media_type="text/html", headers={"Content-Disposition":"attachment; filename=report.html"})
    if body.format not in {"csv","summary"}:
        raise ValueError("Choose csv, summary or html.")
    if body.format=="summary":
        rows = [{"risk_category":key,"count":sum(r["risk_category"]==key for r in rows)} for key in ["low","medium","high"]]
    frame = pd.DataFrame(rows)
    for col in frame.select_dtypes(include="object"):
        frame[col] = frame[col].map(lambda x: "'" + x if isinstance(x,str) and x.lstrip().startswith(("=","+","-","@","\t","\r")) else x)
    return Response(frame.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=predictions.csv"})

@app.delete("/api/models/{model_id}")
def delete_model(model_id: str, request: Request):
    identity=owner(request)
    if model_id.startswith("demo-") or model_id=="local-trained":
        raise HTTPException(403,"Administrator/demo models cannot be deleted here.")
    get_model(model_id,request)
    if identity=="private":
        models.pop(model_id,None);model_owners.pop(model_id,None)
    else:
        from sqlalchemy import delete as sql_delete
        with DB() as db:
            db.execute(sql_delete(Artifact).where(Artifact.id==model_id,Artifact.user_id==identity));db.commit()
    return {"deleted":True}
