import numpy as np
import pytest
from app.ml import synthetic, train, predict

def test_training_schema_and_repeatability():
    data = synthetic()
    a = train(data, "is_fraud")
    b = train(data, "is_fraud")
    p = predict(a, data.head())
    assert np.all((p >= 0) & (p <= 1))
    np.testing.assert_allclose(p, predict(b, data.head()))
    assert sum(a["split"].values()) == len(data)
    assert len(a["threshold_curve"]) == 101
    with pytest.raises(ValueError, match="Missing"):
        predict(a, data[["amount"]])
    with pytest.raises(ValueError, match="missing"):
        predict(a, data.head().assign(amount=np.nan))

def test_artifact_roundtrip(tmp_path):
    import joblib
    data = synthetic()
    bundle = train(data, "is_fraud")
    path = tmp_path / "trusted.joblib"
    joblib.dump(bundle,path)
    restored = joblib.load(path)
    np.testing.assert_allclose(predict(bundle,data.head()), predict(restored,data.head()))

def test_invalid_targets_and_types():
    data = synthetic()
    with pytest.raises(ValueError,match="binary"):
        train(data.assign(is_fraud=2),"is_fraud")
    bundle = train(data,"is_fraud")
    with pytest.raises(ValueError,match="numeric"):
        predict(bundle,data.head().assign(amount="not a number"))

def test_preprocessing_fitted_inside_training_folds():
    from sklearn.model_selection import train_test_split, StratifiedKFold
    data=synthetic()
    bundle=train(data,"is_fraud")
    X=data.drop(columns="is_fraud");y=data.is_fraud
    fit,_,yf,_=train_test_split(X,y,test_size=.2,stratify=y,random_state=42)
    fit,_,yf,_=train_test_split(fit,yf,test_size=.25,stratify=yf,random_state=42)
    indices,_=next(StratifiedKFold(3).split(fit,yf))
    scaler=bundle["model"].calibrated_classifiers_[0].estimator.named_steps["preprocess"].named_transformers_["numeric"].named_steps["scale"]
    np.testing.assert_allclose(scaler.mean_,fit.iloc[indices][bundle["numeric"]].mean().values)
    assert not np.allclose(scaler.mean_,X[bundle["numeric"]].mean().values)
