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
