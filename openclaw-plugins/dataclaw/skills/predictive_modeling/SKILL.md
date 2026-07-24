---
name: predictive_modeling
description: Build a supervised prediction model with leakage-safe validation, an honest baseline, evaluation on the metric that matches the decision, and a check that the model is not learning a proxy of the label.
tags: [modeling, machine-learning, validation, planning, method]
---

# Predictive Modeling Playbook

Use when the goal is genuinely **prediction** — score, rank, or classify units on an outcome — and no causal interpretation is being claimed. The dominant failure modes are **leakage** (the model sees information it will not have at prediction time) and **evaluating against no baseline or the wrong metric**.

## Approach
- Define the **prediction target and the decision** it serves — the metric must match the decision (ranking → AUC / precision@k; calibrated probability → log-loss / Brier; regression → error in the units that matter).
- Start with a **simple baseline**: majority class, a single strong feature, or a linear / logistic model. The complex model must beat it to justify itself.
- Add complexity only if the baseline is insufficient and the data volume supports it.

## Threats to validity (control each)
- **Target leakage** — features computed using the label or post-outcome information (a classic: a field populated only after the event). Audit every feature's availability at prediction time.
- **Train/test contamination** — fit preprocessing inside each fold; keep repeating entities (users, accounts) in a single fold with **group-aware splits**; use **time-based splits** for temporal data.
- **Distribution shift** — the deployment population differs from training; check feature drift.
- **Class imbalance** — accuracy is meaningless; use PR-AUC / recall at the operating point.
- **Overfitting to the validation set** through repeated tuning — hold out a final untouched test set.

## Baseline & evaluation
- Baseline = the simple model above. Report the candidate **relative to it** on the decision metric, with a cross-validated estimate and its spread.
- Evaluate on a held-out set that mirrors deployment (time-forward if temporal). Report calibration when probabilities are used downstream.
- Sanity-check the top features for leakage and plausibility before trusting the score.

## What the plan must state
In `plan_markdown` **Method and rationale**: the target, the decision metric, the model family and why, and the alternatives rejected. In **Baseline, success threshold, and evaluation protocol**: the baseline, the split scheme (group-aware or time-based, with the reason), the held-out test, and the success threshold on the decision metric.

## Execution notes
Log baseline and candidate to MLflow in comparable runs with the same evaluation. Display the leakage / feature audit and the calibration / PR curves. Mark the training / evaluation step high-risk for the `analysis_review` gate.
