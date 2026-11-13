import asyncio
import csv
import io
import json
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from html import escape

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field
from .ml import synthetic, train, predict, explain, validate

models = {}
jobs = {}
executor = ThreadPoolExecutor(max_workers=1)
limits = defaultdict(deque)
log = logging.getLogger("fraudshield")

@asynccontextmanager
async def lifespan(app):
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
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","),
                   allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type", "X-Workspace-Token"])

@app.middleware("http")
async def guard(request: Request, call_next):
    now = time.monotonic()
    key = request.client.host if request.client else "unknown"
    queue = limits[key]
    while queue and queue[0] < now-60:
        queue.popleft()
    if len(queue) >= 120:
        return Response('{"detail":"Rate limit exceeded"}', 429, media_type="application/json")
    queue.append(now)
    if len(limits) > 10000:
        for host in list(limits):
            if not limits[host] or limits[host][-1] < now-60:
                del limits[host]
    length = request.headers.get("content-length")
    if length and int(length) > 2_000_000:
        return Response('{"detail":"Upload limit is 2 MB"}', 413, media_type="application/json")
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response

@app.exception_handler(ValueError)
async def invalid(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=422, content={"detail": str(exc)})

def owner(request):
    configured = os.getenv("WORKSPACE_TOKEN")
    supplied = request.headers.get("x-workspace-token", "")
    if not configured or not secrets.compare_digest(configured, supplied):
        raise HTTPException(401, "Private training requires the server's WORKSPACE_TOKEN.")
    return "private"

def get_model(model_id, request):
    if model_id not in models:
        raise HTTPException(404, "Model not found")
    if not model_id.startswith("demo-"):
        owner(request)
    return models[model_id]

def metadata(key, bundle):
    return {"id": key, **{k:v for k,v in bundle.items() if k not in {"model", "baseline"}}}

class Prediction(BaseModel):
    model_id: str = "demo-logistic"
    records: list[dict[str, float | str]] = Field(min_length=1, max_length=10000)
    threshold: float = Field(default=.5, ge=0, le=1)

class Training(BaseModel):
    records: list[dict[str, float | str]] = Field(min_length=100, max_length=10000)
    target: str
    algorithm: str = "logistic"
    features: list[str] | None = None
    positive_class: str = "1"
    review_cost: float = Field(default=1, gt=0, le=100000)
    missed_cost: float = Field(default=25, gt=0, le=100000)

class Report(Prediction):
    format: str = "csv"

def result(body, request):
    bundle = get_model(body.model_id, request)
    scores = predict(bundle, pd.DataFrame(body.records))
    return [{"transaction_id": str(i+1), **record, "risk_score": float(score),
             "risk_category": "high" if score >= body.threshold else "medium" if score >= body.threshold/2 else "low",
             "prediction": int(score >= body.threshold)} for i,(record,score) in enumerate(zip(body.records,scores))]

@app.get("/api/health")
def health():
    return {"status":"ok", "models_ready": bool(models)}

@app.get("/api/models")
def list_models(request: Request):
    private = os.getenv("WORKSPACE_TOKEN") and secrets.compare_digest(request.headers.get("x-workspace-token",""), os.getenv("WORKSPACE_TOKEN"))
    return [metadata(k,v) for k,v in models.items() if k.startswith("demo-") or private]

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
    return {"method":"Reference feature occlusion, not SHAP", "contributions": explain(bundle, pd.DataFrame(body.records[:1])),
            "limitation":"Changes relative to one reference record; contributions are not additive or causal."}

@app.post("/api/models/train", status_code=202)
def training(body: Training, request: Request):
    owner(request)
    if any(j["status"] in {"queued", "running"} for j in jobs.values()):
        raise HTTPException(409, "One training job is already active.")
    frame = pd.DataFrame(body.records)
    validate(frame)
    if body.target not in frame:
        raise ValueError("Target column is missing.")
    if frame[body.target].isna().any() or frame[body.target].nunique()!=2:
        raise ValueError("Target must have exactly two non-missing classes.")
    labels = frame[body.target].astype(str)
    if body.positive_class not in set(labels):
        raise ValueError("Positive class was not found.")
    frame[body.target] = (labels == body.positive_class).astype(int)
    if body.features:
        if body.target in body.features or set(body.features)-set(frame):
            raise ValueError("Features must exist and exclude the target.")
        frame = frame[body.features + [body.target]]
    identifier = secrets.token_hex(12)
    jobs[identifier] = {"status":"queued"}
    def run():
        jobs[identifier] = {"status":"running"}
        try:
            bundle = train(frame, body.target, body.algorithm, body.review_cost, body.missed_cost)
            models[identifier] = bundle
            jobs[identifier] = {"status":"complete", "model_id":identifier}
        except Exception as exc:
            jobs[identifier] = {"status":"failed", "detail":str(exc)}
    executor.submit(run)
    return {"job_id":identifier}

@app.get("/api/jobs/{job_id}")
def job(job_id: str, request: Request):
    owner(request)
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]

@app.delete("/api/workspace")
def delete(request: Request):
    owner(request)
    if any(j["status"] in {"queued","running"} for j in jobs.values()):
        raise HTTPException(409, "Wait for active training to finish before deleting.")
    for key in list(models):
        if not key.startswith("demo-"):
            del models[key]
    jobs.clear()
    return {"deleted":True}

@app.post("/api/reports")
def report(body: Report, request: Request):
    rows = result(body, request)
    if body.format=="html":
        summary = {"model":body.model_id, "threshold":body.threshold, "rows":len(rows), "flagged":sum(r["prediction"] for r in rows)}
        content = "<!doctype html><html><meta charset='utf-8'><title>FraudShield report</title><h1>Investigation report</h1><pre>"+escape(json.dumps(summary, indent=2))+"</pre><p>Decision support only. Not proof of fraud. Synthetic demo models are not validated on real financial data.</p></html>"
        return Response(content, media_type="text/html", headers={"Content-Disposition":"attachment; filename=report.html"})
    if body.format not in {"csv","summary"}:
        raise ValueError("Choose csv, summary or html.")
    if body.format=="summary":
        rows = [{"risk_category":key,"count":sum(r["risk_category"]==key for r in rows)} for key in ["low","medium","high"]]
    frame = pd.DataFrame(rows)
    for col in frame.select_dtypes(include="object"):
        frame[col] = frame[col].map(lambda x: "'" + x if isinstance(x,str) and x.lstrip().startswith(("=","+","-","@","\t","\r")) else x)
    return Response(frame.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=predictions.csv"})
