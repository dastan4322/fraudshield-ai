# Experimental protocol

Question: how does the threshold affect missed fraud and review workload?

Seed 42 produces 1,200 synthetic records using amount, hour, distance and merchant category.
Labels are sampled from a logistic mechanism. This tests infrastructure, not real fraud efficacy.
Each algorithm receives identical stratified 60/20/20 train/validation/test splits.
A ColumnTransformer imputes/scales numerical values and one-hot encodes categories.
Sigmoid calibration uses three cross-validation folds *inside training*; preprocessing is refit in each fold.
Logistic regression and random forest use balanced class weights; XGBoost provides an unweighted baseline.
Their differences do not isolate the causal effect of weighting: a controlled weighting/SMOTE ablation is not implemented.
Validation selects the least-cost threshold from 101 candidates: FP × review cost + FN × missed-fraud cost.
The test partition is then evaluated at the selected threshold. It never selects the threshold.
The dashboard shows actual PR-AUC, precision, recall, F1, ROC-AUC and Brier error.
API metadata also includes confusion matrix, timing, split sizes and validation cost curve.

Hypothesis: lowering a threshold will typically increase recall and review burden.
Inspect the validation curve in Models & thresholds. Costs are assumptions, not measured financial losses.
Custom training API accepts review_cost and missed_cost. Risk category cutoffs are illustrative.
Calibration is not a guarantee of accuracy under distribution shift.
Synthetic labels partly depend on amount, but explanations must never be treated as causal findings.

Current explanations use feature occlusion relative to one reference row. They are not SHAP or additive.
Chronological evaluation, recall at fixed precision, review-budget comparisons, SHAP summaries,
SMOTE fold-only ablations and global permutation importance remain research extensions.
Anonymized Kaggle V1–V28 features must never be given invented financial meanings.
