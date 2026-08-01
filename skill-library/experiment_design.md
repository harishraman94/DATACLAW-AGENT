---
name: experiment_design
description: Design, analyze, or audit randomized experiments inside the Dataclaw data-science workflow with a defensible randomization unit, power and duration, pre-registered outcomes, assignment and exposure checks, sequential and multiplicity control, and uncertainty at the assignment level. Use for A/B and multivariate tests, cluster or geo experiments, switchbacks, holdouts, factorial designs, non-inferiority, uplift and heterogeneous-treatment analyses, experiment readouts, and sample-size planning.
tags: [experimentation, ab-testing, randomization, causal, method]
---

**Related skills:** `dataclaw_data_science` (governed workflow), `structured_eda` (metric and population readiness), `causal_inference` (non-randomized effects), `feature_engineering` (pre-treatment covariates), `segmentation` (operational targeting), `analysis_review` (validation gate), `visualization`, `report_design`, and `artifacts` (delivery).

# Experiment Design Playbook

Run experiments inside `dataclaw_data_science`; this skill owns randomization, power, analysis, and experiment claim scope. There is no experiment-design tool or plugin to call: power, randomization inference, and estimation run in the notebook with standard libraries such as `statsmodels`, `scipy`, and `numpy`.

Follow this process:

1. Fix the decision, population, eligibility, treatment variants, control, randomization unit, exposure unit, outcome unit, primary estimand, and whether the goal is superiority, non-inferiority, equivalence, or heterogeneous response.
2. Discover data, open the notebook, and fetch `structured_eda`. Establish baseline rate/variance, traffic, clustering, seasonality, exposure latency, repeat users, missing outcomes, and instrumentation stability. Never power on row count when assignment is by user, account, geo, or time block.
3. Choose the design from the routing table. Cluster-randomize when interference crosses individual units; use switchbacks for shared marketplaces or capacity-constrained systems; use stratification/blocking for important prognostic factors.
4. Propose the design with `dataclaw_propose_plan` and wait for approval. Pre-register the primary metric, direction, MDE or non-inferiority margin, alpha, power, allocation, duration, exclusion rules, SRM threshold, analysis model, variance unit, sequential rule, multiplicity family, guardrails, and stopping/refusal conditions.
5. Calculate sample size using the assignment unit, design effect, expected attrition, and planned analysis. Show sensitivity across plausible baseline variance, ICC, and effect sizes; feasibility does not justify silently increasing the MDE.
6. Validate assignment before outcomes: allocation balance/SRM, duplicate assignments, contamination, eligibility drift, exposure logging, and differential missingness. Stop the confirmatory readout on unresolved assignment or instrumentation failure.
7. Estimate intention-to-treat first. Report treatment-on-treated only with a defensible noncompliance strategy. Use CUPED/ANCOVA only with pre-treatment covariates and apply it symmetrically; log the unadjusted estimate too.
8. Report absolute and relative effects with confidence intervals, the pre-registered decision result, guardrails, sample sizes, duration, and exclusions. Correct the declared comparison family; label unplanned segments and metrics exploratory.
9. For heterogeneous effects, use pre-specified segments or honest sample splitting/cross-fitting. Send stable, actionable targeting work to `segmentation`; do not promote a noisy subgroup interaction into a persona.
10. Request analysis review, then deliver the design, integrity checks, estimates, and caveats through the governed reporting flow.

## Design routing

| Constraint | Design | Required caveat |
|---|---|---|
| Independent units, one treatment | Parallel-arm randomized test | Analyze at assignment unit; account for repeat observations |
| Strong prognostic strata | Stratified/block randomization | Include strata in analysis and preserve allocation concealment |
| Interference within groups | Cluster randomized | Inflate power for ICC; use enough clusters and cluster-level uncertainty |
| Shared market/capacity with temporal interference | Switchback | Randomize time blocks; model carryover, seasonality, and autocorrelation |
| Multiple factors | Factorial | Pre-specify interactions; main effects assume no material interaction |
| Persistent control required | Long-lived holdout | Audit contamination and population drift |
| Early stopping required | Group-sequential/always-valid design | Pre-specify looks and boundaries; ordinary repeated p-values are invalid |
| Cannot randomize | `causal_inference` | Do not describe observational adjustment as an experiment |

## Power and analysis contract

- Compute power for the primary estimand and assignment unit. For clusters, include ICC and unequal cluster sizes; for ratios or heavy-tailed revenue, use delta-method, bootstrap, or simulation based on unit-level data.
- Set duration from required independent units plus full outcome maturation and complete business cycles. Novelty is diagnosed, not cured by an arbitrary minimum duration.
- Check SRM against planned allocation before outcome analysis, but also investigate small deviations using assignment logs; a passing aggregate SRM test does not certify assignment.
- Define denominator and exposure estimands: ITT uses all eligible assigned units; per-protocol/exposed-only estimates are secondary and selection-prone.
- Use assignment-level robust or randomization-based uncertainty. For switchbacks, preserve time dependence; for clusters, do not use row-level iid standard errors.
- For non-inferiority/equivalence, justify the margin from decision consequences before the data and use the appropriate one- or two-sided interval decision.

## Threats to validity

- **Peeking/optional stopping** — fixed horizon or valid sequential design only.
- **Multiplicity** — pre-register the family and correction; exploratory results stay exploratory.
- **SRM/assignment failure** — investigate and stop confirmatory interpretation if unresolved.
- **Interference/contamination** — change the randomization unit or model exposure.
- **Attrition/missing outcomes** — compare by arm and bound sensitivity; do not condition on post-treatment completion.
- **Instrumentation change** — version metrics and run an A/A or invariant check when warranted.
- **Novelty, carryover, seasonality** — use event-time diagnostics and a design spanning the relevant cycle.
- **Low cluster count** — asymptotic cluster-robust errors may fail; use randomization inference or small-sample corrections.

## Domain controls

An opt-in domain profile is a technical control bundle, not proof of compliance. Obtain explicit approval for experiments affecting prices, credit, employment, healthcare, or vulnerable populations; define harm guardrails and a human stop owner. Keep identifiers and raw sensitive rows out of outputs; suppress every sensitive output cell below a default 5 units (raise but never lower the floor) with complementary suppression so visible totals cannot reconstruct it. Stop when consent, assignment integrity, or a required safety monitor is unavailable.
