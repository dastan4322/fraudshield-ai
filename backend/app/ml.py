"""Deterministic training, held-out evaluation and schema-bound inference."""
import time
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from sklearn.metrics import average_precision_score, roc_auc_score, precision_score, recall_score, f1_score, confusion_matrix, brier_score_loss, precision_recall_curve, roc_curve
from xgboost import XGBClassifier

SEED = 42

def synthetic():
    rng = np.random.default_rng(SEED)
    n = 1200
    frame = pd.DataFrame({"amount": rng.lognormal(3.5, 1.4, n), "hour": rng.integers(0, 24, n),
                          "distance_km": rng.exponential(40, n), "merchant_category": rng.choice(["retail", "travel", "digital"], n)})
    logit = -4 + .008 * frame.amount + .015 * frame.distance_km + (frame.hour < 5) * 1.3
    frame["is_fraud"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return frame

def validate(frame, features=None):
    if frame.empty or len(frame) > 10000 or len(frame.columns) > 64:
        raise ValueError("Provide 1–10,000 rows and at most 64 columns.")
    if frame.columns.duplicated().any():
        raise ValueError("Duplicate column names are unsupported.")
    if features and set(features) - set(frame):
        raise ValueError("Missing features: " + ", ".join(sorted(set(features) - set(frame))))
    for col in frame.select_dtypes(include="number"):
        if np.isinf(frame[col]).any():
            raise ValueError("Infinite numeric values are unsupported.")

def curves(y, p):
    precision, recall, _ = precision_recall_curve(y,p)
    fpr,tpr,_ = roc_curve(y,p)
    from sklearn.calibration import calibration_curve
    actual,predicted = calibration_curve(y,p,n_bins=10,strategy="quantile")
    budget=max(1,int(len(y)*.05))
    return {"precision_recall":[{"recall":float(r),"precision":float(v)} for r,v in zip(recall,precision)],
            "roc":[{"fpr":float(f),"tpr":float(t)} for f,t in zip(fpr,tpr)],
            "calibration":[{"predicted":float(p),"actual":float(a)} for p,a in zip(predicted,actual)],
            "recall_at_precision_80":float(max(recall[precision>=.8],default=0)),
            "precision_at_review_budget_5pct":float(np.asarray(y)[np.argsort(-p)[:budget]].mean())}

def metrics(y, p, threshold):
    predicted = p >= threshold
    return {"pr_auc": float(average_precision_score(y, p)), "roc_auc": float(roc_auc_score(y, p)),
            "precision": float(precision_score(y, predicted, zero_division=0)),
            "recall": float(recall_score(y, predicted, zero_division=0)), "f1": float(f1_score(y, predicted, zero_division=0)),
            "brier": float(brier_score_loss(y, p)), "confusion_matrix": confusion_matrix(y, predicted, labels=[0,1]).tolist()}

def train(frame, target, algorithm="logistic", review_cost=1., missed_cost=25., split="stratified", weighting=True, smote=False, calibrated=True, parameters=None, time_column=None):
    validate(frame)
    if target not in frame or frame[target].isna().any() or set(frame[target].unique()) != {0, 1}:
        raise ValueError("Target must contain both binary labels 0 and 1 without missing values.")
    if frame[target].value_counts().min() < 20 or len(frame) < 100:
        raise ValueError("Training needs at least 100 rows and 20 examples of each class.")
    features = [c for c in frame if c != target]
    if not features or any(frame[c].nunique() > 500 for c in features if not pd.api.types.is_numeric_dtype(frame[c])):
        raise ValueError("Select features without identifiers or high-cardinality text (maximum 500 categories).")
    if frame[features].duplicated().any():
        raise ValueError("Duplicate feature rows must be resolved before splitting to prevent leakage.")
    text_columns = frame[features].select_dtypes(exclude="number").columns
    if sum(frame[c].nunique() for c in text_columns) > 1000:
        raise ValueError("Combined categorical feature cardinality exceeds 1,000.")
    X, y = frame[features], frame[target]
    if split=="chronological":
        if not time_column or time_column not in X:
            raise ValueError("Chronological splitting requires an explicit time column.")
        order = X.sort_values(time_column).index
        n = len(order)
        a,b = int(n*.6),int(n*.8)
        fit,val,test = X.loc[order[:a]],X.loc[order[a:b]],X.loc[order[b:]]
        yf,yv,yt = y.loc[fit.index],y.loc[val.index],y.loc[test.index]
        if any(v.nunique()!=2 or v.value_counts().min()<6 for v in [yf,yv,yt]):
            raise ValueError("Each chronological partition needs both classes with at least six examples.")
    else:
        fit, test, yf, yt = train_test_split(X, y, test_size=.2, stratify=y, random_state=SEED)
        fit, val, yf, yv = train_test_split(fit, yf, test_size=.25, stratify=yf, random_state=SEED)
    numeric = fit.select_dtypes(include="number").columns.tolist()
    categorical = [c for c in features if c not in numeric]
    preprocess = ColumnTransformer([
        ("numeric", Pipeline([("impute", SimpleImputer(strategy="median", keep_empty_features=True)), ("scale", StandardScaler())]), numeric),
        ("category", Pipeline([("impute", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
                              ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), categorical)])
    classifiers = {"logistic": LogisticRegression(class_weight="balanced", max_iter=500, random_state=SEED),
                   "forest": RandomForestClassifier(n_estimators=80, max_depth=8, class_weight="balanced", n_jobs=1, random_state=SEED),
                   "xgboost": XGBClassifier(n_estimators=80, max_depth=3, n_jobs=1, random_state=SEED)}
    if algorithm not in classifiers:
        raise ValueError("Choose logistic, forest or xgboost.")
    classifier=classifiers[algorithm]
    if not weighting and algorithm in {"logistic","forest"}:
        classifier.set_params(class_weight=None)
    if weighting and algorithm=="xgboost":
        classifier.set_params(scale_pos_weight=float((yf==0).sum()/(yf==1).sum()))
    if parameters:
        classifier.set_params(**parameters)
    steps=[("preprocess",preprocess)]
    if smote:
        from imblearn.over_sampling import SMOTE
        from imblearn.pipeline import Pipeline as ImbalancedPipeline
        steps.append(("smote",SMOTE(random_state=SEED,k_neighbors=2)))
        pipeline=ImbalancedPipeline(steps+[("model",classifier)])
    else:
        pipeline=Pipeline(steps+[("model",classifier)])
    cv=3
    if split=="chronological":
        from sklearn.model_selection import TimeSeriesSplit
        cv=list(TimeSeriesSplit(n_splits=3).split(fit))
        if any(yf.iloc[a].nunique()!=2 or yf.iloc[b].nunique()!=2 for a,b in cv):
            raise ValueError("Chronological calibration folds must each contain both classes.")
    model = CalibratedClassifierCV(pipeline, cv=cv) if calibrated else pipeline
    start = time.perf_counter()
    model.fit(fit, yf)
    elapsed = time.perf_counter() - start
    pv = model.predict_proba(val)[:,1]
    curve = []
    for threshold in np.linspace(0, 1, 101):
        fp = int(((pv >= threshold) & (yv == 0)).sum())
        fn = int(((pv < threshold) & (yv == 1)).sum())
        curve.append({"threshold": float(threshold), "cost": fp * review_cost + fn * missed_cost,
                      "review_count": int((pv >= threshold).sum()), "false_positives": fp, "false_negatives": fn})
    threshold = min(curve, key=lambda r:r["cost"])["threshold"]
    start = time.perf_counter()
    pt = model.predict_proba(test)[:,1]
    latency = (time.perf_counter()-start)*1000/len(test)
    shifted=test.copy()
    for f in numeric:
        if f!=time_column:
            shifted[f]=shifted[f]*1.5
    shift_metrics=metrics(yt,model.predict_proba(shifted)[:,1],threshold)
    return {"model": model, "features": features, "numeric": numeric, "algorithm": algorithm, "target":target, "threshold": threshold,
            "metrics": metrics(yt, pt, threshold), "training_seconds": elapsed, "latency_ms_per_row": latency,
            "threshold_curve": curve, "split": {"train": len(fit), "validation": len(val), "test": len(test)},
            "baseline": fit.iloc[0:1].copy(), "background": fit.sample(min(20,len(fit)),random_state=SEED).copy(),
            "curves":curves(yt,pt), "shift_metrics":shift_metrics, "validation_metrics":metrics(yv,pv,threshold),
            "experiment":{"split":split,"weighting":weighting,"smote":smote,"calibrated":calibrated,"parameters":parameters or {}},
            "version": __import__("hashlib").sha256((frame.to_csv(index=False)+str(parameters)+str(split)+str(weighting)+str(smote)+str(calibrated)+algorithm).encode()).hexdigest()[:16], "source": "custom", "review_cost": review_cost, "missed_cost": missed_cost}

def predict(bundle, frame):
    validate(frame, bundle["features"])
    X = frame[bundle["features"]].copy()
    if X.isna().any().any():
        raise ValueError("Inference requires all feature values; missing values were found.")
    for column in bundle["numeric"]:
        try:
            X[column] = pd.to_numeric(X[column], errors="raise")
        except (ValueError, TypeError):
            raise ValueError(f"Feature {column} must be numeric.")
    validate(X)
    return bundle["model"].predict_proba(X)[:,1]

def explain(bundle, frame):
    """Feature occlusion: change in score after replacing one feature with a reference."""
    p = float(predict(bundle, frame)[0])
    contributions = []
    for feature in bundle["features"]:
        changed = frame.copy()
        changed[feature] = bundle["baseline"][feature].iloc[0]
        contributions.append({"feature": feature, "contribution": p - float(predict(bundle, changed)[0])})
    return sorted(contributions, key=lambda r:abs(r["contribution"]), reverse=True)
