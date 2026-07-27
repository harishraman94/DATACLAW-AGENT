---
name: feature_engineering
description: Build reproducible, leakage-safe model inputs inside the Dataclaw data-science workflow by defining prediction-time availability, excluding identifiers, fitting transforms within folds, cross-fitting target-derived features, handling temporal and grouped data correctly, and versioning feature lineage. Use for tabular, temporal, categorical, text, geospatial, nested, interaction, aggregation, embedding, selection, and dimensionality-reduction features used by predictive, forecasting, causal, uplift, or segmentation models.
tags: [feature-engineering, extraction, leakage, lineage, method]
---

**Related skills:** `dataclaw_data_science` (governed workflow), `structured_eda` (data types and quality), `predictive_modeling`, `forecasting`, `causal_inference`, and `segmentation` (own the model/design evaluation), `analysis_review` (validation gate).

# Feature Engineering Playbook

Feature engineering is a phase inside another method, not a standalone modeling question. This skill owns feature definitions, availability, leakage control, transformations, lineage, and reproducibility; the parent method owns splits, baselines, estimands, metrics, and model selection. There is no feature-engineering tool or plugin to call: construct features in the notebook with standard dataframe and model-pipeline libraries.

Follow this process:

1. Fix the parent method’s unit, index time, prediction/treatment time, horizon, split unit, target/estimand, and deployment inputs. A feature is eligible only if its value and every source event would be available at the decision timestamp.
2. Inventory raw fields with `structured_eda`. Classify each as identifier/join key, target/post-outcome, protected audit attribute, continuous, count, nominal, ordinal, datetime, text, geo, nested, or unavailable at serving time.
3. Create a feature contract before construction: name, definition, source fields, grain, window, cutoff/inclusion boundary, missingness meaning, transformation, availability latency, owner, and expected serving behavior.
4. Audit direct identifiers and high-cardinality near-identifiers. Keep names, emails, phone numbers, account/customer/patient ids, free-text identifiers, and join keys outside the feature matrix; preserve a protected join key separately only when results must be reattached.
5. Propose feature work inside the parent method’s plan. State leakage controls, preprocessing graph, folds, target-derived transformations, temporal windows, selection route, unknown-category behavior, missing-input policy, dimensionality limits, and lineage/version outputs.
6. Build one reproducible `Pipeline`/`ColumnTransformer` or equivalent graph. Fit imputation, scaling, encoding, vectorization, PCA, selection, resampling, and learned aggregations only on training folds.
7. Validate the feature matrix in every fold: row/grain preservation, no future timestamps, stable schema/order/dtypes, finite values, unknown categories, realistic missingness, bounded cardinality, and absence of identifiers/target columns.
8. Compare an auditable raw/minimal feature set against engineered candidates under the parent method’s fixed evaluation. Drop complexity that does not improve out-of-sample decision performance or robustness.
9. Log the fitted pipeline, feature contract, source/version hashes, final feature names, training cutoff, library versions, and validation results to MLflow. Serving must reuse the serialized transform, not reimplement notebook logic.
10. Hand the matrix and audit back to the parent method. Refuse validation when a load-bearing feature cannot be reproduced at serving time or its lineage/cutoff is unknown.

## Transformation routing

| Feature type | Preferred route | Load-bearing rule |
|---|---|---|
| Continuous/count | Impute, transform skew if warranted, scale for scale-sensitive models | Fit parameters inside folds; preserve missingness meaning |
| Nominal categorical | One-hot/ordinal by model, hashing for controlled high cardinality | Define unknown-category behavior; do not encode ids |
| Target/mean/WOE encoding | Cross-fitted encoding with smoothing | Each row’s encoding excludes its own target and validation targets |
| Ordered categorical | Explicit validated order | Do not infer order from lexical or arbitrary numeric codes |
| Temporal event history | Lag/window features with explicit cutoff and closed/open boundary | No event after decision time; account for ingestion latency |
| Repeated entity aggregates | Past-only group aggregates, cross-fitted when target-derived | Prevent the same entity or future rows leaking across folds |
| Text | Fold-fitted vectorizer or versioned embedding model | Remove direct identifiers; pin model/version and truncation |
| Geo | Governed coarse geography, distances, or spatial aggregates | Avoid exact-location leakage and protected-class proxies |
| Dimensionality reduction | Fold-fitted PCA/SVD; supervised selection inside folds | Validate retained information and downstream stability |
| Interactions | Domain-justified or regularized search | Avoid unbounded combinatorial expansion |

## Leakage and reproducibility contract

- **Availability leakage:** use event time plus ingestion/processing latency, not merely the row timestamp. Late-arriving corrections unavailable at decision time are future information.
- **Preprocessing leakage:** fit every data-dependent transform on training data only. A globally fitted vocabulary, imputer, scaler, PCA, or selector contaminates validation.
- **Target leakage:** exclude post-outcome fields; cross-fit any target-derived encoding or aggregate. Never use full-data target statistics as a feature.
- **Entity leakage:** group recurring entities into one fold unless the deployment task explicitly predicts later observations for known entities with a time-forward split.
- **Selection leakage:** perform target-aware selection and dimensionality decisions inside the tuning loop; unsupervised transforms can still leak distributional information if globally fitted.
- **Training-serving skew:** test the serialized pipeline on raw holdout-shaped input, including missing columns, unseen categories, and delayed sources.
- **Lineage:** every output feature must map to source fields, window, transform version, and cutoff. Opaque notebook columns are not deployable features.

## Missingness, cardinality, and drift

Treat missingness as data-generating information: distinguish not-applicable, not-yet-observed, unavailable, and corrupted. Add a missing indicator only when it is available at serving time and improves validated performance; never impute across time from future observations. Collapse rare categories using training-fold counts and an explicit unknown bucket. Monitor source availability, missingness, category churn, range violations, and feature/embedding drift; the parent modeling skill decides retraining or threshold action.

## Domain controls

An opt-in domain profile is a technical control bundle, not proof of compliance. Treat protected attributes as audit fields outside the production matrix unless explicitly authorized; audit proxies before consequential use. Coarsen or exclude precise location, free text, and rare combinations that can re-identify people. Keep raw PII out of model-visible output; suppress every sensitive diagnostic cell below a default 5 units (raise but never lower the floor) with complementary suppression so visible totals cannot reconstruct it. Require human review when feature construction materially changes eligibility, pricing, credit, employment, or care decisions.
