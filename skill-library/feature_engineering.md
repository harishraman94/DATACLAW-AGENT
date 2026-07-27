---
name: feature_engineering
description: Build model inputs without leaking the target — fold-scoped transforms, cross-fitted encodings, temporal availability, leakage-safe selection — a shared phase inside predictive, forecasting, and causal work.
tags: [feature-engineering, extraction, leakage, validation, method]
---

# Feature Engineering Playbook

**Related skills:** `predictive_modeling`, `forecasting`, `causal_inference` (fetch this when their step builds model inputs); `structured_eda` (shows which features matter).

Use whenever you build model inputs — features for `predictive_modeling` or `forecasting`, or covariates for `causal_inference`. It is a **phase inside** those methods, not a separate question. Extraction itself is standard — temporal, text, categorical, and nested/geo fields become typed columns with recorded provenance. The risk that makes this a skill is **leakage**: information the model won't have at prediction time, which inflates validation scores and fails in production.

## Threats to validity (control each)
All of these enforce one rule: *nothing the model uses may depend on data it won't have at prediction time.*
- **Preprocessing leakage** — scalers, imputers, encoders, PCA, or text vectorizers fit on data that includes the validation rows. Fit every transform inside the training fold, then apply to validation; never fit on the full dataset before the split.
- **Target leakage** — features derived from the label or populated at or after the predicted event. Cross-fit target encoding, WOE, and mean-by-group out-of-fold; exclude post-outcome fields.
- **Temporal look-ahead** — lags or rolling windows that peek across the horizon. Every feature must be computable from data available at prediction time.
- **Selection leakage** — feature selection that sees the target must run inside cross-validation, not once on the full dataset, or the validation score is optimistic.
- **Redundancy** — collinear features destabilize estimates; prune or regularize.

## What the plan must state
It has no plan section of its own; it feeds the method playbook's. In `plan_markdown` under **Method and rationale**, state the feature set and extraction steps; under **Assumptions, data limitations, and threats to validity**, state the leakage controls (fold-scoped fitting, cross-fitted encodings, temporal availability). The method playbook's evaluation protocol then validates they hold.

## Execution notes
Load the frame with `dataclaw_data.get_dataframe(...)` and build transforms so they fit per fold — a scikit-learn `Pipeline` / `ColumnTransformer` inside the split, not a global `fit` beforehand. Display a feature-availability / leakage audit before training with `dataclaw_display_cell_output`, record feature definitions with `dataclaw_record_eda_finding` or the plan step `summary`, and log the fitted pipeline to MLflow. This skill adds **no tools of its own**: hand the constructed features back to the method playbook, which owns the split scheme, baseline, and evaluation. If a feature needs a capability the platform does not provide, name the gap; do not invent a feature tool.
