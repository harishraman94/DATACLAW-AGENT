---
name: forecasting
description: Forecast business time series inside the Dataclaw data-science workflow — frame the decision, run leakage-safe rolling-origin backtests against naive baselines, select and generate calibrated time-series forecasts, and run conditional scenarios. Use for demand, revenue, traffic, usage, cost, intermittent or hierarchical series, regressor- or event-driven forecasts, forecast review, and scenario planning.
tags: [forecasting, time-series, validation, planning, method]
---

**Related skills:** `dataclaw_data_science` (governed data, notebook, plan, MLflow, review, and delivery workflow), `structured_eda` (time-series EDA, hypothesis/finding ledger, readiness), `feature_engineering` (fold-safe lag, calendar, event, and regressor inputs), `predictive_modeling` (global/ML forecasters and shared evaluation), `analysis_review` (validation gate), `visualization` (analysis-time charts), `report_design` (final report authorship), `artifacts` (publication and revision).

# Forecasting Playbook

Use when the goal is to predict a business time series forward — demand, revenue, traffic, usage, cost — to serve a decision with a set horizon and update cadence. Forecasting runs inside the `dataclaw_data_science` workflow as notebook code and adds only the forecasting discipline below. There is no forecasting tool or plugin to call: the statistics run in the notebook with standard libraries (statsmodels, statsforecast/sktime). Two failure modes dominate: leakage across the forecast origin, and shipping a model that never beat a naive baseline.

Follow this process:

1. Frame the decision: fix target and units, entity/grain and any hierarchy, forecast horizon, update cadence, the decision served, any point-in-time vintage needs, and the accuracy or coverage threshold that makes the forecast useful.

2. Discover data and run time-series EDA before proposing major work: list datasets with `dataclaw_data_list_datasets`, open a notebook with `dataclaw_open_notebook`, and load frames with `dataclaw_data.get_dataframe(...)`. Fetch `structured_eda` and run time-series diagnostics — STL/seasonality, stationarity, intermittency via ADI/CV², structural breaks. Regularize the series onto an explicit time grid (`resample`/`asfreq`) and separate true gaps, structural zeros, and censored values; they need different treatment. For a quick first pass, seasonally interpolate short gaps, keep flagged outliers, and apply no break treatment. Record frequency, span, seasonality, gap-share, and history-sufficiency with `dataclaw_record_eda_finding`, and confirm modeling readiness with `dataclaw_summarize_eda_readiness` before proposing the plan.

3. Propose a plan with `dataclaw_propose_plan` before execution, and wait for approval. Include the candidate families (a reason for each inclusion and each important exclusion), the rolling-origin protocol, the naive baseline and success threshold, the FVA and coverage minimums, the residual and difference tests, and the refusal conditions — decided now, not during execution. Report progress with `dataclaw_update_plan` after every step status change.

4. Pick candidates from the series shape (routing table below). Always include a naive/seasonal-naive baseline; add complexity only for demonstrated forecast value added (FVA), escalating baselines → classical → regressors/ML/foundation model only when shape, history, cost, and the decision justify it.

5. Run one rolling-origin tournament. Backtest every candidate under one identical configuration (see the backtesting contract below), building fold-scoped inputs with `feature_engineering`. Log each candidate as an MLflow run with comparable metrics and the backtest config, so `dataclaw_query_mlflow_runs` can reconstruct the comparison.

6. Select and generate. The champion must beat the naive baseline on the decision metric; when the difference is not distinguishable, keep the simpler or cheaper model. Generate the operational forecast only by refitting a current admissible champion on eligible history, and return point forecasts, quantiles, and achieved-coverage labels. Refuse to generate without a current backtest, or for an ineligible family. Require explicit user acceptance to generate a candidate that lost to naive, and keep that warning in the output. Label speculative-asset output as backtested pattern extrapolation, not investment advice.

7. Run scenarios and enrichment only when the decision needs them. Keep the unconditional champion — history plus known future regressors — as the reference forecast. Run scenarios on the best admissible regressor-capable candidate across labeled driver paths (baseline, upside, downside) with named owners and assumptions, and disclose its FVA gap when it is not the champion. Keep short-horizon forecastable drivers, such as ~16-day weather, out of the base forecast beyond their reliable window. Before pulling any external driver, present the source, exact query, revealed metadata, cost, and intended feature; fetch only after explicit approval; then test champion-with against champion-without and drop unsupported regressors.

8. Review and deliver. Before marking the step ready for validation, request review with `dataclaw_request_analysis_review` and inspect it with `dataclaw_get_review_gate`; the backtest and selection step is high-risk, so the `analysis_review` gate fires before it is validated. Display the leaderboard, per-horizon errors, recent forecast-vs-actual, the calibrated distribution, residual diagnostics, and scenarios through `visualization`. Deliver through `report_design_report` and `report_publish`, then `publish_artifact`, handing over bounded aggregates, uncertainty, the assumptions and methodology register, and headline caveats; let `report_design` own prose, layout, and HTML.

9. Maintain the forecast. As actuals arrive, re-run the backtest cells, record drift as a finding, and re-tournament when coverage or error degrades.

## Candidate routing by series shape

| Shape | Candidates | Required caveat |
|---|---|---|
| One series, one seasonal period | Naive/seasonal-naive, drift, ETS, Auto-ARIMA/SARIMA, Theta | Add complexity only for demonstrated FVA. |
| Multiple seasonality (daily × weekly × annual) | Seasonal-naive, MSTL, Fourier-ARIMA; TBATS only if justified | Do not use plain SARIMA as if it captures both periods. |
| Intermittent demand | Naive/seasonal-naive, Croston/SBA | If ADI ≥ 1.32 or CV² ≥ 0.49, compare with MASE only, report demand per period, and never use MAPE. |
| Many related series | Per-series classical, global lag models, optional ensembles | Use MCB/Nemenyi-style comparisons; do not cherry-pick per-series wins. |
| Hierarchy | Base forecasts, then reconciliation | Do not ship incoherent totals. |
| Regressor/event driven | Fold-built regressor candidates | Keep only incremental FVA; assumed future regressor values create scenarios, not the base forecast. |
| Short history | Naive/drift/simple ETS with wide intervals | Require ≥2 seasonal cycles (3 preferred), about 30 observations for ARIMA, ~3 cycles or many series for GBMs, and each foundation model’s context window. |

Treat movable holidays as registered regressors, zero-shot foundation models as optional challengers (label public-benchmark contamination risk; select on private-series backtest evidence and cost), and ensembles as ordinary candidates in the same tournament, not a separate workflow.

## Backtesting contract
Use rolling-origin backtesting only: no single train/test cut, no in-sample fit as evidence. Build every data-derived transform — imputation, scaling, encoders, lag/rolling and target-derived features — inside the fold via `feature_engineering`, so nothing peeks across the origin, and exclude imputed points from accuracy denominators. Hold one configuration fixed across every candidate on a shared origin subset: initial window, expanding vs. sliding history, decision horizon, step, refit cadence, maximum origins, and quantiles. Set these from the EDA — the series span, the seasonal period you found, and the decision horizon — not from fixed constants: the initial window must be long enough to identify that seasonality, the step should track the update cadence, and both are chosen to leave enough origins to separate candidates. Initial window and origin count trade off directly; when a short span cannot satisfy both, keep at least two seasonal cycles in the window and report the result as origin-limited rather than shrinking below identifiability.

Rolling origin with the fold boundary made explicit (the helpers are your own notebook code; `StatsForecast.cross_validation` or sktime's `evaluate` package the same loop):

```python
# Set INITIAL, STEP, H from the EDA (span, seasonal period, decision horizon), not from constants.
# Fit every transform on the training slice only; nothing at or after the origin is visible.
rows = []
for origin in rolling_origins(y.index, initial=INITIAL, step=STEP, horizon=H):
    train  = y.loc[:origin]                     # history up to the origin
    feats  = build_fold_features(train)         # fold-safe lags/impute/encoders — the feature_engineering skill
    model  = candidate.fit(train, feats)
    fcst   = model.predict(H, X=regressors_known_at(origin))
    actual = y.loc[origin:].iloc[1:H + 1]
    rows.append(score_by_horizon(actual, fcst, drop_imputed=True))   # imputed actuals leave the denominator
board = leaderboard(rows, baseline=seasonal_naive)   # MASE / sMAPE / pinball / coverage / FVA, by horizon
```

Report by horizon, with origin counts: MASE, a valid sMAPE, pinball loss, interval coverage, and FVA against the naive baseline. Label accuracy indicative below 6 origins and coverage indicative below about 30 origin × horizon observations. Test the champion versus the configured naive baseline and runner-up with a Harvey-Leybourne-Newbold-corrected Diebold-Mariano test on the loss differential, and only with at least 10 origins; otherwise state "insufficient origins to test differences." Check residuals — Ljung-Box at seasonal lags, residual ACF, per-horizon bias — and ship unresolved residual structure as a visible finding.

## Threats to validity (name and control each in the plan)
- **Origin leakage / look-ahead** — a transform or feature fit on data past the origin. Fit per fold, apply forward.
- **Imputed actuals in the denominator** — exclude imputed points from accuracy; set the gap-share limit from the series and imputation method, and refuse or truncate when imputation would carry the accuracy denominator (often well below a ~10% gap-share).
- **Baseline-free evaluation** — always compare to naive/seasonal-naive and report FVA; an unbeaten baseline means no model by default — generate one only under the explicit-acceptance override in step 6, keeping the warning in the output.
- **Backtest overfitting** — from tuning candidates against fixed origins; prefer the simpler or cheaper model when the difference is not testable.
- **Non-stationarity / regime breaks** — a backtest spanning a break may not represent the future; detect breaks in EDA first.

## Domain controls
Turn on a domain profile only when the user activates it; a profile is a technical control bundle, not proof of legal or regulatory compliance. When one is active: for **financial / investment**, label output as backtested pattern extrapolation and never investment advice, and route any forecast that sizes positions or P&L to the documented human sign-off; for **healthcare / pharma demand**, route safety-relevant stockout and supply forecasts to a qualified human and keep validated demand definitions; for **capacity / safety-critical operations** (energy, staffing, inventory), publish coverage and intervals with the point forecast and state the cost of the asymmetric error; for **public sector**, publish the method, the assumptions register, and calibrated uncertainty. Stop the sensitive output if a required control is unavailable.
