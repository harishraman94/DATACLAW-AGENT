---
name: feature_engineering
description: Construct and extract model inputs without leaking the target — fold-scoped transforms, cross-fitted encodings, temporal availability, leakage-safe selection — as a shared phase inside predictive, forecasting, and causal work.
tags: [feature-engineering, extraction, leakage, validation, method]
---

# Feature Engineering Playbook

**Related skills:** `structured_eda` (surfaces which features matter); fetched by `predictive_modeling`, `forecasting`, and `causal_inference` when a step builds model inputs.

Use whenever you are building model inputs — for `predictive_modeling`, `forecasting`, or covariate construction in `causal_inference`. This is a **phase inside** those methods, not a question type; fetch it alongside the method playbook when the step constructs features. Its dominant failure mode is **leakage**: giving the model information it will not have at prediction time, which inflates validation scores and collapses in production.

## Extraction (the constructive front-end)
Turn raw fields into modeling signal, and record each feature's definition and source for the report evidence ledger.
- **Dates/timestamps** — calendar parts, time-since-event, business-day flags; never a feature that encodes the future.
- **Text** — length/counts, TF-IDF, or embeddings; fit the vectorizer/vocabulary on training data only.
- **Categoricals** — one-hot for low cardinality; frequency or **cross-fitted target encoding** for high cardinality (never plain target encoding on the full data — it leaks the label).
- **Geo / JSON / nested** — flatten to typed columns; keep provenance.

## Leakage-safe construction (the core discipline)
- **Fit transforms inside the fold.** Scalers, imputers, encoders, PCA, and feature selection must be fit on the training partition only, then applied to validation — never fit on the full dataset before splitting.
- **Only past-available information.** For temporal data, every feature must be computable from data available at prediction time. Lags and rolling windows must not peek across the horizon.
- **No post-outcome fields.** Exclude anything populated by or after the event being predicted (a classic silent leak).
- **Cross-fit target-derived features.** Target encoding, WOE, and mean-by-group must be computed out-of-fold.
- **Selection is part of the model.** Feature selection that looks at the target must happen inside cross-validation, not once on all data — otherwise the validation score is optimistic.

## Threats to validity (name and control each)
- **Target leakage** — post-outcome or label-derived features. Audit every feature's availability at prediction time.
- **Preprocessing leakage** — transforms fit on data that includes the validation rows.
- **Temporal look-ahead** — features using future information for a past prediction.
- **Selection leakage** — choosing features on the full dataset before validation.
- **Redundancy / dimensionality** — many collinear features destabilize estimates; prune or regularize.

## What the plan must state
In `plan_markdown`, under **Method and rationale** and **Threats to validity**: the feature set you will build and why, the extraction steps, and the explicit leakage controls (fold-scoped fitting, cross-fitted encodings, temporal availability). The evaluation protocol in the method playbook then validates that these controls hold.

## Execution notes
Implement transforms so they can be fit per fold (e.g. a pipeline), not once globally. Display a feature-availability/leakage audit before training and record feature definitions for the report. Hand the constructed features back to the method playbook's evaluation step, which owns the split scheme and baseline.
