---
name: survey_analytics
description: Analyze survey, poll, questionnaire, tracker, and panel data inside the Dataclaw data-science workflow — pin the sample design and question bases, screen quality, estimate weighted toplines and crosstabs with design-based variance, compare groups and waves correctly, run drivers/segmentation/factor work, and code open-text verbatims under governance. Use for Google Forms, SurveyMonkey, Qualtrics, or SPSS/CSV/Parquet survey data, NPS and Likert and multi-select analysis, weighted and unweighted results, and evidence-bound survey reporting.
tags: [survey, sampling, weighting, verbatim, method]
---

**Related skills:** `dataclaw_data_science` (governed data, notebook, plan, review, and delivery workflow), `structured_eda` (survey EDA, hypothesis/finding ledger, readiness), `experiment_design` (randomized survey experiments), `causal_inference` (effect claims from observational data), `feature_engineering` (leakage-safe outcome-linkage inputs), `segmentation` (general clustering and typing discipline; this skill governs attitudinal-battery latent-class methods), `analysis_review` (validation gate), `visualization` (analysis-time charts), `report_design` (final report authorship), `artifacts` (publication and revision).

# Survey Analytics Playbook

Use when the data is survey responses — poll, questionnaire, tracker, panel, or open-text verbatims — analyzed to serve a decision for a defined audience. Survey analysis runs inside the `dataclaw_data_science` workflow as notebook code and adds only the survey discipline below. There is no survey tool or plugin to call: the statistics run in the notebook with standard libraries (`samplics` for design-based estimation and weighting; `factor_analyzer` and `pingouin` for scale structure and reliability; `dominance-analysis` for driver importance; `krippendorff` for coding agreement). Two failure modes dominate: computing a percentage on the wrong base, and treating a nonprobability sample as if it carried sampling-error precision.

Follow this process:

1. Frame the decision: fix the research question, the decision served, the audience and deliverable, and the unit of analysis — what one row is (respondent, respondent × wave, occasion, dyad) and any nesting or rollup. Classify the sample as probability, quota/opt-in panel, or census, and record field dates, mode, and wave/version.

2. Discover data and pin the survey contract before proposing major work: list datasets with `dataclaw_data_list_datasets`, open a notebook with `dataclaw_open_notebook`, and load frames with `dataclaw_data.get_dataframe(...)`. Fetch `structured_eda`. For each question, establish the eligible base (who was actually asked), the Likert value order, the multi-select delimiter, the missing codes, and any reverse coding; identify the analytic weight, any replicate weights, strata, and PSU/cluster. Treat inferred bases, roles, and delimiters as provisional until confirmed — never split every comma blindly, and keep detected PII out of model-visible output. Record base, nonresponse, weighting, small-group, and instrument-version risks with `dataclaw_record_eda_finding`, and confirm readiness with `dataclaw_summarize_eda_readiness`.

3. Screen quality before estimating. Flag duplicates, speeders (e.g. under ~40% of median completion time), and straightliners as separate signals, then apply one explicit inclusion rule. Treat every threshold as a heuristic: report sample composition before and after, and show sensitivity for any judgment-based exclusion.

4. Propose a plan with `dataclaw_propose_plan` before execution, and wait for approval. Include the estimand and eligible base per question, the weighting scheme and variance method, the comparison family and multiplicity correction, effect-size reporting, the small-cell suppression rule, and the refusal conditions — decided now, not during execution. Report progress with `dataclaw_update_plan` after every step status change.

5. Estimate with the design, not with plain arithmetic. Compute each estimate on its eligible base and carry design-based variance from `samplics`. Prefer an honestly labeled unweighted result to an unjustified weight; keep analytic and replicate weights distinct and never pass a replicate-weight column as the one analysis weight; report the design effect and Kish effective n; and do not attach a sampling-error MOE to opt-in or other nonprobability samples — label those as descriptions of respondents, not population estimates.

```python
import dataclaw_data
from samplics.estimation import TaylorEstimator

df = dataclaw_data.get_dataframe(dataset_id="DATASET_ID", table_name="main.responses")
eligible = df[df["asked_q1"]]                      # the question's base, not all rows
est = TaylorEstimator("proportion")
est.estimate(y=eligible["q1"], samp_weight=eligible["w_analytic"],
             stratum=eligible["stratum"], psu=eligible["psu"])
print(est.point_est, est.stderror)                 # design-based estimate + SE, not a plain SE
```

6. Describe and compare correctly (method routing below). Preserve Likert order and justify any mean on an ordinal scale beside an ordinal view; state the multi-select denominator and why shares can exceed 100%; compute NPS as %promoters − %detractors, with uncertainty from a difference of multinomial proportions — promoter and detractor variances and their negative covariance — not a single-proportion SE. Match the test to the design: never apply independent-group tests to panels, dyads, repeated responses, or clustered accounts. In trackers, mark any wording, option, mode, or sample change as a trend break, and distinguish repeated cross-sections from panels.

7. Run advanced analysis only when the question needs it (routing below). Treat drivers and outcome linkage as associational unless `causal_inference` supplies an identification design, and use relative-importance methods over raw coefficient ranking. For segmentation, match the method to the measurement level — latent class / latent profile analysis for categorical or ordinal batteries (model selection by BIC and entropy), and k-means only on genuinely continuous derived scores — and require multi-seed stability and usable segment sizes before profiling. Respect reverse coding in factor and reliability work, and do not re-score a validated instrument without its authorized scoring spec.

8. Code open text as a governed loop (contract below), not a free-form summarize.

9. Review and deliver. Before marking the step ready for validation, request review with `dataclaw_request_analysis_review` and inspect it with `dataclaw_get_review_gate`; weighted estimation and group comparison are high-risk, so the `analysis_review` gate fires before validation. Display based toplines, crosstabs, driver importance, and segment profiles through `visualization`. Deliver through `report_design_report` and `report_publish`, then `publish_artifact`, handing over based estimates, uncertainty, methodology, limitations, and the evidence ledger; let `report_design` own prose, layout, and HTML.

## Method routing by question type

| Question type | Method | Required caveat |
|---|---|---|
| Single categorical / Likert topline | Weighted proportion via `samplics` (Taylor or replicate) | Compute on the eligible base; preserve Likert order. |
| Two-group / subgroup comparison | Design-based contrast (Rao-Scott / survey-weighted test) | Match to dependence; no independent-group test on panels, dyads, or clusters. |
| Multi-select | Per-option proportions on the asked base | State the denominator; shares can exceed 100%. |
| NPS | %promoters − %detractors | Difference of proportions from one multinomial: SE from promoter and detractor variances plus their negative covariance, not a single-proportion SE. |
| Key drivers | Relative importance (`dominance-analysis`) | Associational unless `causal_inference` identifies; never rank raw coefficients. |
| Segmentation | Latent class / profile analysis (`stepmix`) for categorical/ordinal or mixed items; k-means only on continuous derived scores, multi-seed | Match method to measurement level — don't cluster Likert items as interval. Require usable sizes and stable, distinct, interpretable profiles. |
| Scale / reliability | EFA/CFA + reliability (`factor_analyzer`, `pingouin`) | Respect reverse coding; don't re-score a validated instrument. |
| MaxDiff / conjoint / TURF | Choice models (`torch-choice`, `xlogit`); TURF greedy search | Refuse without the design and task inputs. |

## Weighting and variance contract
Use design-based estimation for every population estimate. For calibrated or raked weights, require target compatibility, convergence, trimming disclosure, the design effect, effective n, and estimate sensitivity to alternative trimming/calibration choices before reporting; a raking failure must be diagnosable, not silent. Refuse a design-based margin of error when no complex-sample or replication design path is available, and never attach one to a nonprobability sample by default. Weighting to known margins does not remove nonresponse bias: report item and unit nonresponse, and run a sensitivity check when missingness on a key variable could change the answer. Carry the base (unweighted n), denominator, weight label, and effective n with every material estimate.

## Open-text coding contract
1. Draft a versioned codeframe — stable ids, definitions, inclusions, exclusions, examples, and an explicit `other`/uncodable path — from a small, PII-redacted, stratified sample. Get ordinary user approval in chat.
2. Before bulk LLM coding, disclose response and batch counts, rough token cost, and the destination, then proceed only after explicit approval — it costs money and verbatims may carry personal detail.
3. Validate every batch's code ids deterministically. Verify a sample stratified by code, rarity, and model uncertainty; report per-code precision/recall and a chance-corrected agreement (Krippendorff α via `krippendorff`) with uncertainty; predeclare the pass/revision rule.
4. Block theme prevalence while the codeframe is draft or unverified. Identity-strip quotes and apply the same small-base rules as tables. Persist the codeframe and coding progress with `dataclaw_ws_write_file`; if a durable coding-state tool is later added it would enforce resumability and eligibility, but nothing here requires one.

## Threats to validity (name and control each in the plan)
- **Wrong base / denominator** — a percentage over all rows instead of who was asked. Register the eligible base per question; do not infer a skip from nulls.
- **False precision on nonprobability samples** — a sampling MOE on an opt-in panel. Label opt-in results as descriptions of respondents; attach an interval only with a defensible model.
- **Replicate-weight misuse** — passing a replicate-weight column as the analysis weight. Keep analytic and replicate weights distinct.
- **Dependence ignored** — independent-group tests on panels, dyads, repeated responses, or clustered accounts. Match the test to the design.
- **Measurement-level mismatch** — clustering ordinal Likert items with k-means treats them as interval (its centroids are means). Segment categorical/ordinal batteries with latent class/profile analysis; reserve k-means for continuous scores.
- **Unverified themes** — theme prevalence from a draft or unverified codeframe. Block prevalence until verified and report agreement.
- **Trend breaks** — comparing waves across wording, option, mode, or sample changes. Mark them as breaks; distinguish cross-sections from panels.
- **Multiplicity** — many comparisons inflating false positives. Predeclare the comparison family and correct.

## Domain controls
Turn on a domain profile only when the user activates it; a profile is a technical control bundle, not proof of legal or regulatory compliance. When one is active: for **healthcare / pharma**, preserve validated scoring and route adverse-event signals to a qualified human; for **employee research**, suppress any group cell, crosstab count, or quote drawn from fewer than a default 5 respondents (raise the floor in the plan for smaller or more sensitive populations; never lower it) and apply complementary suppression so published margins cannot back-solve a suppressed small cell; for **financial services**, route vulnerability and complaint flags to the documented human process; for **public sector**, use the declared complex design and publish design-based uncertainty. Stop the sensitive output if a required control is unavailable.
