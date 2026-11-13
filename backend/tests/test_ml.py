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
