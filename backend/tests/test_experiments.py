import numpy as np
import pytest
from app.ml import synthetic,train

@pytest.mark.parametrize("algorithm",["logistic","forest","xgboost"])
@pytest.mark.parametrize("variant",["baseline","smote","chronological"])
def test_training_protocols(algorithm,variant):
    data=synthetic().assign(event_order=np.arange(1200))
    options={"weighting":False} if variant=="baseline" else {"smote":True,"weighting":False} if variant=="smote" else {"split":"chronological","time_column":"event_order"}
    bundle=train(data,"is_fraud",algorithm,**options)
    assert 0<=bundle["metrics"]["pr_auc"]<=1
    assert bundle["curves"]["precision_recall"]
    assert bundle["curves"]["roc"]
    assert len(bundle["version"])==16

def test_time_column_and_fold_guards():
    with pytest.raises(ValueError,match="time column"):
        train(synthetic(),"is_fraud",split="chronological")
    data=synthetic().sort_values("is_fraud").reset_index(drop=True).assign(event_order=np.arange(1200))
    with pytest.raises(ValueError,match="partition"):
        train(data,"is_fraud",split="chronological",time_column="event_order")

def test_kaggle_fixture_schema():
    from app.ml import predict
    data=synthetic()
    fixture=data[["amount","hour","distance_km"]].rename(columns={"amount":"Amount","hour":"Time","distance_km":"V1"})
    for i in range(2,29):
        fixture[f"V{i}"]=np.random.default_rng(i).normal(size=len(data))
    fixture["Class"]=data.is_fraud
    bundle=train(fixture,"Class")
    assert len(bundle["features"])==30
    assert len(predict(bundle,fixture.head(3)))==3
    with pytest.raises(ValueError,match="Missing"):
        predict(bundle,fixture.drop(columns="V28").head())

def test_duplicate_features_cannot_leak_across_splits():
    import pandas as pd
    data=synthetic()
    with pytest.raises(ValueError,match="Duplicate feature"):
        train(pd.concat([data,data.head(1)],ignore_index=True),"is_fraud")
