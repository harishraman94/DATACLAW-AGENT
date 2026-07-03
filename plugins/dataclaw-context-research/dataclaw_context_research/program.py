"""Research programs: hypotheses, enrichment candidates, and experiment branches."""

from __future__ import annotations

from collections import Counter
from typing import Any

from dataclaw_data.registry import find_dataset


def build_research_program(
    *,
    dataset_id: str = "",
    problem_statement: str = "",
    findings: list[dict[str, Any]] | None = None,
    max_hypotheses: int = 8,
) -> dict[str, Any]:
    findings = findings or []
    dataset = find_dataset(dataset_id) if dataset_id else {}
    schema_terms = _schema_terms(dataset)
    domain_terms = _domain_terms(problem_statement, findings, schema_terms)
    target = _target_guess(problem_statement, schema_terms)

    hypotheses = _hypotheses(
        problem_statement=problem_statement,
        findings=findings,
        schema_terms=schema_terms,
        target=target,
        limit=max_hypotheses,
    )
    external_data = _external_data_candidates(problem_statement, findings, domain_terms)
    experiment_branches = _experiment_branches(hypotheses, external_data, dataset_id=dataset_id)
    return {
        "dataset_id": dataset_id,
        "problem_statement": problem_statement,
        "domain_terms": domain_terms,
        "target_guess": target,
        "source_summary": _source_summary(findings),
        "hypotheses": hypotheses,
        "external_data_candidates": external_data,
        "experiment_branches": experiment_branches,
        "subagent_tasks": _subagent_tasks(experiment_branches),
        "feedback_loop": {
            "baseline_required": True,
            "compare_against": "provided-data-only baseline",
            "metrics_to_track": [
                "validation metric improvement",
                "generalization gap",
                "data leakage risk",
                "external-data coverage",
                "feature stability",
                "fairness/bias diagnostics where applicable",
            ],
            "iteration_rule": (
                "Promote an enrichment or hypothesis only when it improves validation performance "
                "without increasing leakage risk or degrading robustness diagnostics."
            ),
        },
        "caveats": [
            "External data must be license-compatible and time-aligned with the prediction/analysis target.",
            "Community/forum findings are weak signals; use them for hypotheses, not final claims.",
            "Every promoted feature should have an ablation result against the baseline.",
        ],
    }


def program_markdown(program: dict[str, Any]) -> str:
    return f"""---
title: "Research Program"
kind: "research_program"
tags:
  - "context-research"
  - "hypotheses"
  - "experiments"
---

# Research Program

## Objective

{program.get("problem_statement") or "No explicit problem statement was provided."}

## Source Summary

{_dict_lines(program.get("source_summary", {}))}

## Hypotheses

{_hypothesis_lines(program.get("hypotheses", []))}

## External Data Candidates

{_external_lines(program.get("external_data_candidates", []))}

## Experiment Branches

{_branch_lines(program.get("experiment_branches", []))}

## Subagent Tasks

{_task_lines(program.get("subagent_tasks", []))}

## Feedback Loop

{_dict_lines(program.get("feedback_loop", {}))}

## Caveats

{chr(10).join(f"- {c}" for c in program.get("caveats", []))}
"""


def _schema_terms(dataset: dict[str, Any]) -> list[str]:
    terms = []
    for table in dataset.get("tables") or []:
        terms.append(str(table.get("name", "")))
        for column in table.get("column_details") or []:
            terms.append(str(column.get("name", "")))
    return [t for t in terms if t]


def _domain_terms(problem_statement: str, findings: list[dict[str, Any]], schema_terms: list[str]) -> list[str]:
    tokens = Counter()
    for text in [problem_statement, *schema_terms, *(f.get("title", "") for f in findings), *(f.get("snippet", "") for f in findings)]:
        for token in _tokens(str(text)):
            tokens[token] += 1
    return [term for term, _ in tokens.most_common(20)]


def _target_guess(problem_statement: str, schema_terms: list[str]) -> str:
    joined = " ".join([problem_statement, *schema_terms]).lower()
    for candidate in ("saleprice", "churn", "default", "fraud", "readmission", "score", "rating", "performance", "distress", "risk"):
        if candidate in joined:
            return candidate
    return ""


def _hypotheses(
    *,
    problem_statement: str,
    findings: list[dict[str, Any]],
    schema_terms: list[str],
    target: str,
    limit: int,
) -> list[dict[str, Any]]:
    base = []
    if findings:
        for finding in findings[: max(1, limit)]:
            title = finding.get("title", "external finding")
            source = finding.get("source", "external")
            evidence = finding.get("evidence_level", "unverified")
            base.append({
                "id": f"h{len(base) + 1}",
                "statement": f"Insights from '{title}' may improve the solution if adapted to this dataset.",
                "rationale": f"Source: {source}, evidence: {evidence}. Use as a testable hypothesis, not an assumption.",
                "signals_to_test": _signals_from_text(f"{title} {finding.get('snippet', '')}", schema_terms),
                "expected_effect": "Potential lift over provided-data-only baseline if the idea captures missing domain structure.",
                "risk": "May not transfer; validate with ablation and leakage checks.",
                "source_ids": [finding.get("id", "")],
            })
            if len(base) >= limit:
                break
    if len(base) < limit:
        base.extend([
            {
                "id": f"h{len(base) + 1}",
                "statement": "Temporal/order-aware features may improve performance if observations have sequence or recency structure.",
                "rationale": "Many real-world problems encode behavior over time even when raw rows look static.",
                "signals_to_test": ["lag/rolling aggregates", "session order", "recency"],
                "expected_effect": "Better generalization for behavior or forecasting tasks.",
                "risk": "High leakage risk if future information is included.",
                "source_ids": [],
            },
            {
                "id": f"h{len(base) + 2}",
                "statement": "External domain covariates may explain variance missing from the provided dataset.",
                "rationale": "Provided data is often an incomplete view of the real-world system.",
                "signals_to_test": ["public statistics", "calendar effects", "geographic or market context"],
                "expected_effect": "Improved robustness on scenarios underrepresented in training data.",
                "risk": "External joins can introduce coverage bias or stale context.",
                "source_ids": [],
            },
        ])
    if target:
        base[0]["target_context"] = target
    return base[:limit]


def _external_data_candidates(problem_statement: str, findings: list[dict[str, Any]], domain_terms: list[str]) -> list[dict[str, Any]]:
    candidates = [
        {
            "name": "Official/public domain statistics",
            "search_query": f"{' '.join(domain_terms[:5])} public dataset statistics",
            "use_case": "Add macro/domain context not present in the uploaded dataset.",
            "validation": "Join coverage, temporal alignment, license, and ablation lift.",
            "risk": "Mismatch between public aggregates and row-level entities.",
        },
        {
            "name": "Calendar and event context",
            "search_query": f"{' '.join(domain_terms[:5])} calendar events holidays seasonality",
            "use_case": "Capture seasonality, interventions, events, or policy shifts.",
            "validation": "Time-split validation and leakage audit.",
            "risk": "Can leak future events if not cut by prediction date.",
        },
    ]
    for finding in findings[:4]:
        candidates.append({
            "name": f"Source-linked enrichment: {finding.get('title', 'external source')}",
            "search_query": f"{finding.get('title', '')} dataset code features",
            "use_case": "Investigate whether this cited source exposes datasets, benchmarks, or feature recipes.",
            "validation": "Source license, reproducibility, feature ablation, and train/test coverage.",
            "risk": "Paper/repo may not provide reusable data or may be domain-mismatched.",
            "source_id": finding.get("id", ""),
            "url": finding.get("url", ""),
        })
    return candidates


def _experiment_branches(hypotheses: list[dict[str, Any]], external_data: list[dict[str, Any]], *, dataset_id: str) -> list[dict[str, Any]]:
    branches = []
    for hypothesis in hypotheses[:6]:
        branches.append({
            "id": f"exp-{hypothesis['id']}",
            "name": hypothesis["statement"][:80],
            "dataset_id": dataset_id,
            "hypothesis_id": hypothesis["id"],
            "steps": [
                "Reproduce provided-data-only baseline and record metric.",
                "Engineer features or enrichments implied by the hypothesis.",
                "Run validation with leakage-safe split.",
                "Compare against baseline with ablation.",
                "Report lift, failure mode, and whether to promote or reject.",
            ],
            "success_criteria": "Improves validation metric while passing leakage and robustness checks.",
        })
    if external_data:
        branches.append({
            "id": "exp-external-data-audit",
            "name": "External data discovery and join feasibility audit",
            "dataset_id": dataset_id,
            "hypothesis_id": "",
            "steps": [
                "Inspect candidate external sources for accessible datasets or reproducible feature recipes.",
                "Check licenses, coverage, join keys, and time alignment.",
                "Prototype one safe join/enrichment only if feasibility is high.",
                "Run ablation against baseline.",
            ],
            "success_criteria": "Finds at least one license-compatible enrichment with measurable lift or useful negative evidence.",
        })
    return branches


def _subagent_tasks(branches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "task_id": f"task-{branch['id']}",
            "branch_id": branch["id"],
            "title": branch["name"],
            "recommended_subagent": "analysis-experimenter",
            "task": (
                f"Run experiment branch {branch['id']}: {branch['name']}. "
                f"Steps: {'; '.join(branch['steps'])}. "
                "Return baseline metric, enriched metric, ablation result, leakage risks, artifacts, and promote/reject recommendation."
            ),
        }
        for branch in branches
    ]


def _source_summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "findings": len(findings),
        "by_source_type": dict(Counter(f.get("source_type", "unknown") for f in findings)),
        "by_evidence": dict(Counter(f.get("evidence_level", "unverified") for f in findings)),
    }


def _signals_from_text(text: str, schema_terms: list[str]) -> list[str]:
    lower = text.lower()
    hits = [term for term in schema_terms if term and term.lower() in lower]
    generic = [t for t in ("feature engineering", "sequence", "fairness", "missing data", "tree model", "external data") if t in lower]
    return (hits + generic)[:8] or ["domain-inspired feature set", "baseline comparison"]


def _tokens(text: str) -> list[str]:
    import re

    stop = {"with", "from", "this", "that", "data", "model", "using", "based", "and", "the", "for"}
    return [t for t in re.split(r"[^a-zA-Z0-9]+", text.lower()) if len(t) > 3 and t not in stop]


def _dict_lines(values: dict[str, Any]) -> str:
    return "\n".join(f"- {k}: `{v}`" for k, v in values.items()) or "- None"


def _hypothesis_lines(items: list[dict[str, Any]]) -> str:
    lines = []
    for item in items:
        lines.append(f"### {item.get('id')}: {item.get('statement')}")
        lines.append(f"- Rationale: {item.get('rationale')}")
        lines.append(f"- Signals to test: `{item.get('signals_to_test', [])}`")
        lines.append(f"- Expected effect: {item.get('expected_effect')}")
        lines.append(f"- Risk: {item.get('risk')}\n")
    return "\n".join(lines) or "- No hypotheses generated."


def _external_lines(items: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- **{item.get('name')}**: {item.get('use_case')} Query: `{item.get('search_query')}` Risk: {item.get('risk')}"
        for item in items
    ) or "- No external data candidates generated."


def _branch_lines(items: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"- **{item.get('id')}**: {item.get('name')} Success: {item.get('success_criteria')}"
        for item in items
    ) or "- No experiment branches generated."


def _task_lines(items: list[dict[str, Any]]) -> str:
    return "\n".join(f"- **{item.get('task_id')}**: {item.get('task')}" for item in items) or "- No subagent tasks generated."
