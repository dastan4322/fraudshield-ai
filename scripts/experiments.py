"""Reproducible validation-only Optuna search and controlled holdout experiments."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import optuna
from app.ml import train, predict, metrics, synthetic

def run(frame, target, trials=3, time_column=None, source="fixture"):
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    report={"dataset":source,"sha256":hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest(),
            "hypothesis":"Threshold and imbalance strategy change recall, calibration and investigation burden.",
            "seed":42,"limitations":["One holdout per protocol; not a banking certification.","Search uses validation PR-AUC only; never select parameters using test results."],"runs":[]}
    for algorithm in ["logistic","forest","xgboost"]:
        def objective(trial):
            parameters={"C":trial.suggest_float("C",.05,10,log=True)} if algorithm=="logistic" else {"max_depth":trial.suggest_int("max_depth",2,8)}
            bundle=train(frame,target,algorithm,parameters=parameters)
            return bundle["validation_metrics"]["pr_auc"]
        study=optuna.create_study(direction="maximize",sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective,n_trials=trials)
        for label,options in [("baseline",{"weighting":False}),("class-weighted",{"weighting":True}),
                              ("SMOTE",{"weighting":False,"smote":True}),("uncalibrated",{"calibrated":False})]:
            bundle=train(frame,target,algorithm,parameters=study.best_params,**options)
            record={k:v for k,v in bundle.items() if k not in {"model","baseline","background"}}
            record.update({"algorithm":algorithm,"variant":label,"best_validation_pr_auc":study.best_value,
                           "hypothesis":f"{label} affects review workload and probability quality.","dataset":source})
            record["distribution_shift_stress"]=bundle["shift_metrics"]
            record["distribution_shift_limitation"]="Fixed 1.5x scaling of held-out test numeric features, excluding time; stress scenario only, never used in selection."
            from app.explanations import shap_explain
            record["shap_sample_importance"]=shap_explain(bundle,frame.head(5))["global_importance"]
            record["cost_sensitivity"]=[{"missed_cost":c,"threshold":min(bundle["threshold_curve"],key=lambda r:r["false_positives"]+r["false_negatives"]*c)["threshold"]} for c in [5,25,100]]
            report["runs"].append(record)
        if time_column:
            try:
                bundle=train(frame,target,algorithm,split="chronological",time_column=time_column)
                report["runs"].append({"variant":"chronological","algorithm":algorithm,"selection":"Fixed defaults; stratified search parameters are not reused across chronological partitions.",**{k:v for k,v in bundle.items() if k not in {"model","baseline","background"}}})
            except ValueError as exc:
                report["runs"].append({"variant":"chronological","algorithm":algorithm,"selection":"Fixed defaults; stratified search parameters are not reused across chronological partitions.","status":"rejected","reason":str(exc)})
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--csv")
    parser.add_argument("--target",default="is_fraud")
    parser.add_argument("--time-column")
    parser.add_argument("--trials",type=int,default=3)
    parser.add_argument("--output",default="artifacts/experiments.json")
    args=parser.parse_args()
    frame=pd.read_csv(args.csv) if args.csv else synthetic().assign(event_order=np.arange(1200))
    if args.csv and args.target=="Class":
        required={"Time","Amount","Class"}|{f"V{i}" for i in range(1,29)}
        if set(frame)!=required:
            raise ValueError("Kaggle schema requires Time, Amount, V1–V28, Class.")
    if len(frame)>10000:
        raise ValueError("Experiment runner limit: 10,000 rows. Make and document a stratified sample first.")
    result=run(frame,args.target,args.trials,args.time_column or ("event_order" if not args.csv else None),
               "Kaggle creditcard.csv (user supplied)" if args.csv and args.target=="Class" else args.csv or "synthetic fixture")
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,allow_nan=False))
    print(f"Saved {len(result['runs'])} experiment runs to {path}")
