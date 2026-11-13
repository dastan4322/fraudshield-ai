"""Permutation SHAP over the complete calibrated preprocessing/classification pipeline."""
import numpy as np
import pandas as pd
import shap
from .ml import predict

def shap_explain(bundle, frame):
    predict(bundle, frame)  # enforce the inference schema before explaining
    features = bundle["features"]
    background = bundle.get("background", bundle["baseline"]).copy()
    categories = {f:list(background[f].dropna().astype(str).unique()) for f in features if f not in bundle["numeric"]}
    def encode(df):
        output = []
        for f in features:
            if f in categories:
                values = categories[f]
                output.append(df[f].astype(str).map(lambda v: values.index(v) if v in values else len(values)).to_numpy(float))
            else:
                output.append(pd.to_numeric(df[f]).to_numpy(float))
        return np.array(output).T
    # Extend the vocabulary to include explained categories; never refit the trained model.
    for f, values in categories.items():
        values.extend(v for v in frame[f].astype(str).unique() if v not in values)
    def probability(encoded):
        decoded = pd.DataFrame(encoded, columns=features)
        for f, values in categories.items():
            decoded[f] = decoded[f].map(lambda v: values[min(max(int(round(v)),0),len(values)-1)])
        return bundle["model"].predict_proba(decoded)[:,1]
    masker = shap.maskers.Independent(encode(background), max_samples=20)
    explainer = shap.Explainer(probability, masker, algorithm="permutation", feature_names=features, seed=42)
    explanation = explainer(encode(frame[features].head(20)), max_evals=2*len(features)+1)
    values = np.asarray(explanation.values)
    return {"method":"Permutation SHAP", "output":"calibrated positive-class probability",
            "base_values":np.asarray(explanation.base_values).tolist(), "values":values.tolist(),
            "features":features, "global_importance":[{"feature":f,"mean_abs_shap":float(np.abs(values[:,i]).mean())} for i,f in enumerate(features)],
            "contributions":[{"feature":f,"contribution":float(values[0,i])} for i,f in enumerate(features)],
            "predictions":probability(encode(frame[features].head(20))).tolist(),
            "sample_count":len(values), "limitation":"Interventional SHAP over at most 20 submitted records and 20 training background records. Approximate, background-dependent and not causal; anonymized V features have no inferred real-world meaning."}
