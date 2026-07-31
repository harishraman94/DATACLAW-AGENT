---
name: causal_inference
description: Estimate and defend causal effects inside the Dataclaw data-science workflow by choosing an identification strategy, stating the estimand, testing design-specific assumptions, quantifying uncertainty, and refusing unsupported causal claims. Use for impact analysis, policy or treatment effects, difference-in-differences, matching or weighting, instrumental variables, regression discontinuity, synthetic controls, interrupted time series, mediation questions, and observational “does X cause Y?” requests.
tags: [causal, inference, impact, econometrics, method]
---

**Related skills:** `dataclaw_data_science` (governed notebook, plan, review, and delivery workflow), `structured_eda` (design-focused EDA and readiness), `experiment_design` (randomized treatment), `feature_engineering` (pre-treatment covariates), `predictive_modeling` (nuisance models only), `analysis_review` (validation gate), `visualization` (diagnostics), `report_design` and `artifacts` (delivery).

# Causal Inference Playbook

Run causal work inside `dataclaw_data_science`; this skill owns identification, estimation, assumptions, and causal claim scope. There is no causal-inference tool or plugin to call: estimate in the notebook with standard libraries such as `statsmodels`, `linearmodels`, `econml`, `dowhy`, or `doubleml` only when the selected design warrants them. Prediction or covariate adjustment alone does not identify an effect.

Follow this process:

1. Define the intervention, outcome, unit, treatment timing, comparison condition, population, horizon, and estimand (ATE, ATT, CATE, LATE, local RDD effect). Draw or state the causal structure: pre-treatment confounders, mediators, colliders, instruments, and plausible interference.
2. Discover data with `dataclaw_data_list_datasets`, open the notebook with `dataclaw_open_notebook`, load through `dataclaw_data.get_dataframe(...)`, and fetch `structured_eda`. Audit treatment/outcome timing, overlap, missingness, attrition, repeated units, anticipation, spillovers, and whether the outcome definition changed.
3. Choose the strongest defensible design from the routing table before choosing an estimator. If no design identifies the effect, refuse the causal claim and offer an explicitly associational analysis.
4. Propose the design with `dataclaw_propose_plan` and wait for approval. State the estimand, identifying assumption, falsification/diagnostic checks, nuisance models, uncertainty method, sensitivity analysis, negative controls/placebos, refusal conditions, and alternatives rejected. Update status with `dataclaw_update_plan`.
5. Build only pre-treatment covariates with `feature_engineering`. Never control for mediators, colliders, or variables first observed after treatment. Fit preprocessing and nuisance models within the relevant folds.
6. Estimate the naive association and the identified effect. Use clustered, heteroskedasticity-robust, randomization-based, or bootstrap uncertainty at the assignment/sampling level; never default to row-level iid errors when units repeat or treatment is clustered.
7. Run the design-specific diagnostics and at least one sensitivity or falsification check. Diagnose overlap before propensity weighting; trim or change the estimand rather than extrapolating across unsupported regions.
8. Report the effect with interval, estimand, population, time window, identifying assumption, diagnostic results, and sensitivity range. Do not convert a local effect into a population-wide claim.
9. Request `dataclaw_request_analysis_review`, inspect `dataclaw_get_review_gate`, then deliver diagnostics through `visualization` and the final evidence-bound report through `report_design` and `artifacts`.

## Identification strategy routing

| Available design | Use | Load-bearing checks |
|---|---|---|
| Treatment randomized | `experiment_design` | Assignment integrity, SRM, attrition, noncompliance, interference |
| Treated/control units before and after | Difference-in-differences / event study | No anticipation; credible untreated counterfactual; pre-period dynamics; treatment timing; unit/time clustering |
| One/few treated aggregate units with long pre-period | Synthetic control | Pre-treatment fit, donor contamination, leave-one-out/placebo effects |
| Rich pre-treatment confounders with overlap | Matching, weighting, doubly robust AIPW/DML | Positivity, post-adjustment balance, weight tails, unmeasured confounding sensitivity |
| Valid external treatment shifter | Instrumental variables | Relevance, exclusion, independence, monotonicity; report LATE |
| Deterministic threshold assignment | Sharp/fuzzy RDD | Manipulation, bandwidth sensitivity, covariate continuity, functional-form sensitivity |
| Clearly dated intervention in one series | Interrupted time series | Existing trend/seasonality, concurrent shocks, autocorrelation, enough pre/post observations |

Staggered-adoption DiD requires a cohort/time estimator that does not use already-treated units as untreated controls; do not rely on a single two-way fixed-effects coefficient when effects vary by cohort or time. A pre-trend test that fails to reject is not proof of parallel trends: show event-time estimates, contextual support, and sensitivity to differential trends.

## Estimation and validation contract

- Define the target trial or observational analogue before estimation: eligibility, treatment strategies, assignment, follow-up, outcome, causal contrast, and analysis.
- Require common support for adjustment designs. Report standardized mean differences after adjustment and the effective sample size/weight distribution; extreme weights trigger trimming, overlap weighting, or a narrower estimand.
- Cross-fit flexible nuisance models for AIPW/DML; tune them for nuisance prediction without selecting the causal result. Report the simple design-based estimate alongside the advanced estimator.
- Use negative-control outcomes/exposures, placebo dates/groups, alternative bandwidths/control groups, or a quantified unmeasured-confounding sensitivity appropriate to the design.
- Treat mediation as a separate identification problem requiring assumptions about mediator-outcome confounding; do not read mechanisms from coefficient attenuation.

## Threats to validity

- **Unmeasured confounding** — no adjustment removes an omitted common cause; quantify sensitivity and bound the claim.
- **Positivity failure** — unsupported treatment regions force extrapolation; change population/estimand or refuse.
- **Post-treatment conditioning** — mediators and colliders bias the effect; exclude them from adjustment.
- **Treatment timing and anticipation** — align eligibility and follow-up; exclude contaminated pre-periods.
- **Interference** — model exposure or cluster at the interference unit; SUTVA is not automatic.
- **Attrition and missing outcomes** — compare by treatment and model plausible missingness; bound when unverifiable.
- **Specification search** — decide primary design, outcome, horizon, and sensitivity grid in the plan, not after seeing significance.

## Domain controls

Use only an opt-in domain profile; it is a technical control bundle, not proof of compliance. Keep direct identifiers and raw sensitive rows out of model-visible output. For healthcare, employment, credit, pricing, or public policy, require qualified human review, subgroup/equity diagnostics, documented treatment eligibility, and suppress every sensitive output cell below a default 5 units (raise but never lower the floor) with complementary suppression so visible totals cannot reconstruct it. Never recommend consequential action from an unidentified or positivity-violating effect.
