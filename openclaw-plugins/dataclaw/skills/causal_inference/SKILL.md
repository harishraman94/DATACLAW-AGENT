---
name: causal_inference
description: Choose and justify a causal identification strategy (experiment, difference-in-differences, matching, instrumental variables, regression discontinuity) for cause-and-effect questions, with the assumptions and validity threats each requires.
tags: [causal, inference, planning, method]
---

# Causal Inference Playbook

**Related skills:** `experiment_design` (when treatment can be randomized), `feature_engineering` (covariate construction), `analysis_review` (validation gate before the step is marked ready).

Use this when the question is about **cause and effect** — "does X drive Y", "what is the impact of", "if we change X, what happens to Y" — not about prediction ("what predicts Y"). A predictive model answers the wrong question here and will mislead: it captures association, confounded by everything that moves with X.

## Pick an identification strategy
Use the strongest one the data supports.
- **Randomized experiment / A/B test** — if treatment can be (or was) randomized. Gold standard; if a live test is feasible, fetch `experiment_design` instead.
- **Difference-in-differences (DiD)** — a treated group and a comparable control group observed before and after the change. Rests on **parallel trends** (both groups moving together pre-treatment); verify with a pre-period trend plot.
- **Matching / propensity weighting** — no time dimension, but rich covariates that plausibly capture confounding. Match treated to similar untreated units and check covariate balance after matching. Assumes **no unmeasured confounders** (strong).
- **Instrumental variables (IV)** — an instrument that shifts treatment but affects the outcome only through treatment. Needs relevance (strong first stage) and exclusion (defended on domain grounds, not testable).
- **Regression discontinuity (RDD)** — treatment assigned by a threshold on a running variable. Estimates a local effect near the cutoff; check for manipulation of the running variable (density test).

If none of these identify the effect, say so: report the association explicitly labeled as non-causal, naming the confounders that block a causal claim.

## Threats to validity (name and control each in the plan)
- **Confounding** — common causes of treatment and outcome. Control via design, not by adding predictors to a model.
- **Selection bias** — who ends up treated is related to the outcome.
- **Reverse causality** — Y drives X. Use timing/lags to rule out.
- **Post-treatment bias** — never condition on variables affected by the treatment.
- **Spillover / SUTVA** — one unit's treatment affecting another's outcome.

## Baseline & evaluation
- Baseline = the naive confounded estimate (raw difference in means). Show it, then show how the design moves the estimate — the gap is the confounding you removed.
- Report an effect size **with a confidence interval**, not a point estimate or a p-value alone. Be explicit about the estimand (ATE / ATT / LATE).
- Run at least one **robustness / sensitivity check**: a placebo test (effect should vanish where none is expected), an alternative control group, or sensitivity to an unmeasured confounder.

## What the plan must state
In `plan_markdown` **Method and rationale**: the chosen strategy, the specific assumption it rests on, how you will check that assumption, and the alternatives rejected (especially "predictive model — rejected, answers association not causation"). In **Baseline, success threshold, and evaluation protocol**: the naive baseline, the estimand, the confidence-interval approach, and the robustness check.

## Execution notes
Capture the assumption checks (parallel-trends plot, covariate balance, first-stage strength) as notebook cells and display them. Log the estimate, CI, and robustness results to MLflow. Mark the estimation step high-risk so the `analysis_review` gate fires before it is validated.
