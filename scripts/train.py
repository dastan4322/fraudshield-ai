"""Train only trusted local CSVs; generated joblib files must never be uploaded by users."""
import argparse
import json
from pathlib import Path
import joblib
import pandas as pd
from app.ml import train
parser = argparse.ArgumentParser()
parser.add_argument("csv")
parser.add_argument("--target", default="Class")
parser.add_argument("--algorithm", choices=["logistic","forest","xgboost"], default="logistic")
parser.add_argument("--output", default="artifacts")
args = parser.parse_args()
frame = pd.read_csv(args.csv)
# Kaggle contract, including original feature ordering.
if args.target == "Class":
    required = ["Time"] + [f"V{i}" for i in range(1,29)] + ["Amount", "Class"]
    if set(frame) != set(required):
        raise ValueError("Kaggle input requires Time, V1–V28, Amount and Class.")
    frame = frame[required]
# CLI permits the full Kaggle dataset by deterministically selecting a bounded training subset.
if len(frame)>10000:
    from sklearn.model_selection import train_test_split
    frame, _ = train_test_split(frame, train_size=10000, stratify=frame[args.target], random_state=42)
bundle = train(frame, args.target, args.algorithm)
out = Path(args.output)
out.mkdir(parents=True, exist_ok=True)
joblib.dump(bundle, out / "model.joblib")
(out / "metrics.json").write_text(json.dumps({k:v for k,v in bundle.items() if k not in {"model","baseline"}}, indent=2))
print((out / "metrics.json").read_text())
