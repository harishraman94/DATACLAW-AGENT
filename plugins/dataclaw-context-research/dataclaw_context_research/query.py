"""Concept-driven query generation for open-world context research."""

from __future__ import annotations

import re
from typing import Any

from dataclaw_data.registry import find_dataset


STOP_WORDS = {
    "id", "ids", "key", "name", "date", "time", "type", "status", "value",
    "count", "number", "num", "total", "table", "data", "file", "csv",
    "train", "test", "sample", "submission",
}

DOMAIN_HINTS = {
    "healthcare": {"patient", "diagnosis", "readmission", "hospital", "a1c", "glucose", "claim", "provider"},
    "finance": {"loan", "credit", "default", "balance", "transaction", "fraud", "claim", "premium", "risk"},
    "retail": {"product", "sales", "store", "customer", "sku", "order", "price", "quantity", "inventory"},
    "real estate": {"saleprice", "garage", "lot", "zoning", "basement", "bedroom", "bath", "property"},
    "saas": {"churn", "subscription", "mrr", "arr", "plan", "account", "tenant", "usage"},
    "mobility": {"trip", "pickup", "dropoff", "fare", "driver", "vehicle", "route", "latitude", "longitude"},
    "survey": {"survey", "response", "rating", "score", "satisfaction", "nps", "question"},
    "climate": {"temperature", "rainfall", "emissions", "weather", "carbon", "station", "precipitation"},
}

OBJECTIVE_HINTS = {
    "prediction": {"target", "label", "outcome", "price", "default", "churn", "readmission", "fraud"},
    "forecasting": {"date", "time", "month", "week", "demand", "sales", "volume"},
    "segmentation": {"customer", "user", "account", "cluster", "segment"},
    "anomaly detection": {"fraud", "outlier", "alert", "incident", "failure"},
}


def generate_queries(
    *,
    dataset_id: str = "",
    problem_statement: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    context = _collect_context(dataset_id=dataset_id, problem_statement=problem_statement)
    concepts = _extract_concepts(context)
    domain = _infer_label(concepts, DOMAIN_HINTS) or "data analysis"
    objective = _infer_label(concepts, OBJECTIVE_HINTS) or "analysis"
    target_terms = _target_terms(concepts)

    base = f"{domain} {objective}".strip()
    queries = [
        f"{base} common pitfalls data quality",
        f"{base} methodology best practices",
        f"{base} feature engineering",
        f"{base} bias privacy ethics risks",
        f"{base} missing data handling",
    ]
    for term in target_terms[:4]:
        queries.append(f"{domain} {term} interpretation data analysis")
    if problem_statement:
        queries.insert(0, _compact(problem_statement))

    deduped = []
    seen = set()
    for query in queries:
        normalized = " ".join(query.split()).lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(query)
    return {
        "queries": deduped[: max(1, int(limit))],
        "inferred_domain": domain,
        "inferred_objective": objective,
        "concepts": concepts[:30],
    }


def _collect_context(*, dataset_id: str, problem_statement: str) -> list[str]:
    pieces = [problem_statement] if problem_statement else []
    if dataset_id:
        dataset = find_dataset(dataset_id)
        pieces.extend([
            str(dataset.get("name", "")),
            str(dataset.get("description", "")),
            str(dataset.get("definition", "")),
        ])
        for table in dataset.get("tables") or []:
            pieces.append(str(table.get("name", "")))
            for column in table.get("column_details") or []:
                pieces.append(str(column.get("name", "")))
    return pieces


def _extract_concepts(parts: list[str]) -> list[str]:
    tokens: list[str] = []
    for part in parts:
        for raw in re.split(r"[^a-zA-Z0-9]+", _camel_to_words(part).lower()):
            if len(raw) < 3 or raw in STOP_WORDS:
                continue
            tokens.append(raw)
    ranked = sorted(set(tokens), key=lambda token: (-tokens.count(token), token))
    return ranked


def _infer_label(concepts: list[str], hints: dict[str, set[str]]) -> str:
    concept_set = set(concepts)
    best = ("", 0)
    for label, words in hints.items():
        score = len(concept_set & words)
        if score > best[1]:
            best = (label, score)
    return best[0]


def _target_terms(concepts: list[str]) -> list[str]:
    priority = [c for c in concepts if c in {"target", "label", "outcome", "price", "churn", "default", "fraud", "score", "rating", "sales", "revenue"}]
    return priority + [c for c in concepts if c not in priority]


def _camel_to_words(value: str) -> str:
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)


def _compact(value: str) -> str:
    return " ".join(value.split())[:180]
