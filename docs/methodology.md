# ML methodology and experiments

## Protocol
All demo and committed experiment results use synthetic data, seed 42. They are not Kaggle measurements.
Numerical imputation/scaling and categorical one-hot encoding are fitted within each training fold.
Default stratified splits are 60% training, 20% validation, 20% test.
Sigmoid calibration fits three train-only folds. SMOTE, when enabled, is inside the imbalanced-learn pipeline,
so neither validation nor test data is resampled. Exact duplicate feature rows are rejected before splitting.

Chronological experiments sort by an explicit numeric time column, use fixed model defaults,
and use expanding-window calibration folds inside the first 60%. They do not reuse hyperparameters
selected on stratified partitions, which could include chronological future test data.
Partitions or calibration folds without both labels are rejected.

Optuna's seeded search maximizes validation PR-AUC only. The report records baseline, weighted,
SMOTE and uncalibrated variants for each model and a chronological run: 15 runs total.
The committed fixture run uses two search trials per algorithm; it is a smoke experiment, not exhaustive optimization.
Hyperparameter trials compute test predictions internally, but no test result enters the objective or threshold selection.
Do not choose future variants by these reported test scores and then call the same test partition untouched.

The validation threshold minimizes FP × review_cost + FN × missed_cost on a 101-point grid.
The test set is evaluated at that fixed threshold.
Reports contain PR/ROC/calibration curves, precision, recall, F1, PR-AUC, ROC-AUC, Brier error and confusion matrices.
They also include recall at precision ≥80%, precision at a 5% review budget, validation cost sensitivity,
and a fixed distribution-shift stress test (1.5× held-out numerical features, excluding time).
The stress scenario is not a forecast of deployment performance.

## Reproduce
```bash
PYTHONPATH=backend python scripts/experiments.py --trials 2 --output artifacts/synthetic-experiments.json
PYTHONPATH=backend python scripts/experiments.py --csv /path/creditcard-sample.csv --target Class --time-column Time --trials 20
```
The bounded runner accepts up to 10,000 rows; document any sampling from the full Kaggle dataset.
Download the real dataset with Kaggle's supported CLI after installing `kaggle` and configuring your own credentials:
```bash
python scripts/download_kaggle.py --output data/kaggle
```
Or download manually from https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud.
Credentials are never embedded, copied into configuration, or invented. Do not redistribute data without permission.
The cloud proxy denied Kaggle access during this run, and Kaggle authentication was not configured.
Kaggle schema and inference are tested using generated fixtures with Time, V1–V28, Amount, Class.
Real benchmark results remain blocked by dataset access.

## SHAP
Permutation SHAP wraps the full calibrated pipeline, including preprocessing, for all three model types.
A 20-row training background is encoded reversibly for categorical masking. Up to 20 requested rows are explained.
Per-row SHAP values sum with the base value to the predicted positive-class probability (tested).
The UI shows global mean absolute attribution over the requested sample, individual contributions and a record-by-feature summary.
This bounded sample is not a claim of full-population importance. Explanations are approximate, background-dependent
and not causal. PCA features V1–V28 have no invented financial identities.

## Interpretation
[Committed experiment results](synthetic-experiments.json) contain only aggregate metrics, curves and feature importances.
They contain no transaction records. Model-to-model differences are not evidence that one method always wins.
SMOTE on one-hot encoded categories can create fractional encoded vectors; treat this as a research comparison,
not a validated production method for arbitrary categorical datasets.
Synthetic label mechanisms, small positive class counts, one random seed and distribution shift limit conclusions.
A public benchmark cannot establish accuracy, fairness, regulatory compliance or suitability for a bank.
