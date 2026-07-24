---
name: forecasting
description: Design a time-series forecasting approach with leakage-safe rolling-origin backtesting, a seasonal-naive baseline every model must beat, and the stationarity/seasonality checks that drive method choice.
tags: [forecasting, time-series, validation, planning, method]
---

# Forecasting Playbook

Use for predicting a quantity over future time — demand, revenue, load, churn timing. The failure modes are **temporal leakage** (using future information to predict the past) and **evaluating against no baseline**, which makes a mediocre model look good.

## Method choice follows the data
- Inspect first: trend, seasonality (and its period), missing periods, level shifts, and whether the series is stationary.
- **Seasonal-naive / naive** — always compute this first. It is the baseline every model must beat.
- **Classical (ETS, ARIMA / SARIMA)** — strong for a single series with clear trend/seasonality and limited exogenous drivers.
- **Regression / gradient boosting on lag & calendar features** — when exogenous regressors matter and you have many series or rich covariates. Guard feature leakage (only past-available features).
- **Global / hierarchical models** — many related series; reconcile forecasts if totals must add up.

## Threats to validity (control each)
- **Temporal leakage** — never shuffle. Split by time; features must use only information available at prediction time.
- **Look-ahead in preprocessing** — fit scalers/imputers on the training window only, inside each fold.
- **Non-stationarity / regime change** — a level shift mid-series breaks a model trained across it; consider differencing or recent-window training.
- **Horizon overfitting** — evaluate at the horizon you actually care about, not one step ahead if the decision is weeks out.

## Baseline & evaluation
- Baseline = seasonal-naive (or naive for non-seasonal). Report the model **relative to it** (e.g. MASE, or % MAE reduction). A model that does not beat seasonal-naive is not a result.
- Use **rolling-origin backtesting** (expanding or sliding window), not a single train/test cut — multiple origins give a stable error estimate and expose horizon degradation.
- Report error at the decision horizon with an interval, plus a forecast-vs-actual plot over the backtest.

## What the plan must state
In `plan_markdown` **Method and rationale**: the method and why it fits the observed trend / seasonality / exogenous structure, with alternatives rejected. In **Baseline, success threshold, and evaluation protocol**: the seasonal-naive baseline, the backtest scheme (origins, window, horizon), the metric relative to baseline, and the success threshold.

## Execution notes
Build the backtest as a reusable notebook function; display fold-by-fold error and the forecast-vs-actual plot. Log baseline and model metrics to MLflow in the same run for a direct comparison. Mark the modeling step high-risk for the `analysis_review` gate.
