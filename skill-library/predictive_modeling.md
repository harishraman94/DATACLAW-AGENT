---
name: predictive_modeling
description: Build, evaluate, calibrate, and operationalize supervised prediction models inside the Dataclaw data-science workflow with leakage-safe validation, decision-aligned metrics and thresholds, honest baselines, subgroup and shift checks, uncertainty, and deployment monitoring. Use for classification, regression, ranking, propensity or risk scores, churn and fraud prediction, lead scoring, probability calibration, model comparison, model cards, and audits of existing predictive systems.
tags: [modeling, machine-learning, prediction, validation, method]
---

**Related skills:** `dataclaw_data_science` (governed workflow), `structured_eda` (target and population readiness), `feature_engineering` (model inputs), `forecasting` (time-indexed prediction), `causal_inference` (effect claims), `segmentation` (typing and value/risk tiers), `analysis_review` (validation gate), `visualization`, `report_design`, and `artifacts` (delivery).

# Predictive Modeling Playbook

Run prediction inside `dataclaw_data_science`; this skill owns target framing, split design, baselines, evaluation, selection, calibration, and operational monitoring. It does not authorize causal claims. Standard model training runs in the notebook with libraries such as `scikit-learn`, `xgboost`, or `lightgbm`; do not invent a predictive-modeling tool.

Follow this process:

1. Define the decision, prediction unit, target event/value, observation window, prediction time, forecast horizon, eligible population, action capacity, error costs, and how a score changes an action. If no action or evaluation population can be named, do not optimize a model yet.
2. Discover data, open a notebook, and fetch `structured_eda`. Audit label provenance, censoring/delay, prevalence, repeated entities, temporal drift, missing-label selection, leakage candidates, identifiers, protected attributes, and mismatch between training and deployment populations.
3. Choose the task and evaluation route from the table. Use `forecasting` when the primary dependence is time-series forecasting and `causal_inference` when the question is intervention impact.
4. Propose the plan and wait for approval. State the target contract, feature availability cutoff, split scheme, frozen test set, baseline, candidate families, tuning budget, primary decision metric, minimum improvement, threshold/capacity rule, calibration, subgroup/fairness checks, uncertainty, and refusal conditions.
5. Fetch `feature_engineering`. Put every learned transform, selection step, resampling step, and target-derived encoding inside the training fold. Exclude direct identifiers; treat protected attributes as audit variables unless their use is explicitly justified and governed.
6. Fit a naive/business baseline and a transparent linear/tree baseline before complex candidates. Evaluate all candidates on identical folds and log comparable MLflow runs with seeds, data/version identifiers, parameters, metrics, and fitted pipelines.
7. Select using cross-validation or nested cross-validation without touching the final test. Freeze the model and threshold, then evaluate once on a deployment-mirroring holdout; do not repeatedly tune against it.
8. Report discrimination/error, calibration when scores are probabilistic, performance at the operating threshold or capacity, uncertainty, subgroup results, coverage/abstention, and improvement over baseline. AUC alone never establishes operational value.
9. Stress deployment: temporal/out-of-domain slices, plausible feature drift, missing inputs, extreme values, and delayed labels. Define monitoring for input drift, score drift, calibration/performance decay, outcome availability, threshold volume, and retraining triggers.
10. Request analysis review and deliver an evidence-bound model card/report. Do not ship the model when the target is invalid, the test set is contaminated, key groups have unmeasured performance, or deployment inputs cannot reproduce training features.

## Task and metric routing

| Decision | Primary evaluation | Required caveat |
|---|---|---|
| Rank a limited queue | Precision/recall or gain/lift at capacity; PR-AUC | Evaluate at the actual review/contact capacity |
| Produce probabilities | Log loss/Brier plus calibration curve/slope | Recalibrate only on validation data; audit by subgroup |
| Binary action with asymmetric costs | Expected utility/cost at a frozen threshold | State false-positive/false-negative costs and prevalence |
| Continuous prediction | MAE/RMSE/quantile loss in decision units | Inspect heteroskedasticity and tail errors |
| Rare-event detection | PR-AUC, recall at alert budget, false positives per unit time | Accuracy and ROC-AUC can hide operational burden |
| Ordinal outcome | Ordinal loss, weighted kappa, threshold metrics | Do not flatten order into unrelated classes |
| Time-indexed future values | `forecasting` | Use rolling-origin evaluation and time-aware baselines |

## Validation and selection contract

- Split by the leakage unit: group repeated users/accounts, split forward for temporal deployment, and preserve site/geography boundaries when transport is the risk.
- Use nested CV when tuning/search is material and data is limited. Report fold spread or bootstrap intervals; a single score is not evidence.
- Compare against prevalence/mean, current business rule, and a simple interpretable model. Complexity must produce decision-relevant improvement, not merely a tiny metric gain.
- Select the operating threshold from validation data using declared costs, capacity, or sensitivity constraints. Lock it before final test evaluation and report confusion-matrix counts/rates at that point.
- Calibrate on held-out or cross-fitted predictions. Report reliability, not only discrimination; recalibration does not repair covariate or concept shift.
- For imbalanced data, resample or weight only inside training folds and evaluate on the natural deployment prevalence.
- Use subgroup metrics with adequate uncertainty and intersectional checks when decisions affect people. Do not claim fairness from aggregate parity or suppress evidence of poor performance in a small group.
- Prefer interpretable diagnostics appropriate to the model; feature importance and SHAP are predictive associations, not causal explanations.

## Threats to validity

- **Label leakage and target proxies** — audit availability at prediction time and remove post-outcome fields.
- **Label selection/censoring** — model the eligible labeled population and bound claims when outcomes are missing selectively.
- **Entity/time contamination** — group- or time-aware splits prevent memorization and look-ahead.
- **Validation overfitting** — nested tuning plus a single frozen final test.
- **Prevalence/threshold mismatch** — evaluate at deployment prevalence, costs, and capacity.
- **Distribution and concept shift** — stress slices and define monitoring/retraining triggers.
- **Feedback loops** — predictions change who receives an action and therefore which labels return; retain exploration/audit samples.
- **Proxy discrimination** — keep protected attributes for auditing, exclude or govern their use, and inspect correlated proxies.

## Domain controls

An opt-in profile is a technical control bundle, not proof of compliance. For credit, pricing, employment, healthcare, safety, or fraud, require qualified human review, contestability/override paths, subgroup uncertainty, and explicit abstention/escalation. Keep identifiers and raw sensitive rows out of model-visible output; suppress every sensitive output cell below a default 5 units (raise but never lower the floor) with complementary suppression so visible totals cannot reconstruct it. Never auto-deploy or change a consequential threshold without explicit approval.
