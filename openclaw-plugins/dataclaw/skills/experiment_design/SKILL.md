---
name: experiment_design
description: Design or evaluate a controlled experiment (A/B test, uplift) — randomization unit, power and sample size, a pre-registered primary metric, and an analysis that avoids peeking and multiple-comparison inflation.
tags: [experimentation, ab-testing, causal, planning, method]
---

# Experiment Design Playbook

Use when a change can be (or was) randomized and the question is its causal effect. Randomization is the strongest identification there is — the work is in designing it correctly and analyzing it honestly. If treatment cannot be randomized, fetch `causal_inference` instead.

## Design decisions (settle before any data)
- **Unit of randomization** — user, session, account, geo? Match it to the level at which the effect and any interference occur. Cluster (e.g. geo) when spillover between users is likely.
- **Primary metric** — one pre-registered success metric with a direction and a minimum detectable effect (MDE). Secondary metrics are exploratory, not success criteria.
- **Power & sample size** — compute required N from baseline rate, MDE, α, and power (0.8+). State the run length; do not stop early on a peek.
- **Guardrail metrics** — what must not get worse (latency, revenue, retention).

## Threats to validity (control each)
- **Peeking / optional stopping** — checking significance repeatedly inflates false positives. Fix the horizon, or use a sequential test designed for it.
- **Multiple comparisons** — many metrics or segments inflate false positives; correct (e.g. Benjamini-Hochberg) or pre-register the few that count.
- **Sample-ratio mismatch (SRM)** — a split that is not the intended ratio signals broken assignment; check it first and stop if it fails.
- **Interference / network effects** — one unit's treatment leaking to control; cluster-randomize.
- **Novelty / primacy effects** — early behavior differs from steady state; run long enough.

## Baseline & evaluation
- Baseline = the control arm. Report the treatment effect as a **difference with a confidence interval**, plus the primary-metric result against the pre-registered threshold.
- Check SRM and guardrails before reading the primary result.
- For uplift / heterogeneous effects, pre-specify segments; treat post-hoc segment findings as hypotheses, not conclusions.

## What the plan must state
In `plan_markdown` **Method and rationale**: the randomization unit, the primary metric + MDE, and why this design identifies the effect. In **Baseline, success threshold, and evaluation protocol**: the power calculation and N, the fixed horizon, the SRM and guardrail checks, and the multiple-comparison handling.

## Execution notes
Compute power / sample size in a notebook cell up front and display it. Check SRM before analysis. Log the design parameters and the effect estimate + CI to MLflow. Mark the analysis step high-risk for the `analysis_review` gate.
