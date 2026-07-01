"""Tests for open-world context research plugin."""

from __future__ import annotations

from pathlib import Path

import pytest

import dataclaw.config.paths as paths
from dataclaw_data.registry import create_dataset
from dataclaw_context_research.query import generate_queries
from dataclaw_context_research.reddit import parse_reddit_search
from dataclaw_context_research.registry import filter_findings, read_findings
from dataclaw_context_research.tools import (
    context_research_list_findings,
    context_research_save_to_okf,
    context_research_search_reddit,
    context_research_summarize_findings,
)
from dataclaw_okf.generator import generate_bundle


@pytest.fixture(autouse=True)
def tmp_home(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "DATACLAW_HOME", tmp_path)
    return tmp_path


@pytest.fixture
def survey_dataset(tmp_path):
    csv_path = tmp_path / "customer_survey.csv"
    csv_path.write_text(
        "respondent_id,nps_score,satisfaction_rating,churn_flag,comment_text\n"
        "1,10,5,0,love it\n"
        "2,2,1,1,too expensive\n",
        encoding="utf-8",
    )
    return create_dataset(
        name="Customer Survey",
        ds_type="csv",
        connection=str(csv_path),
        description="Customer feedback and retention survey",
    )


def test_generate_queries_uses_schema_as_concept_signal(survey_dataset):
    result = generate_queries(
        dataset_id=survey_dataset["id"],
        problem_statement="Understand why customers churn after poor satisfaction scores",
    )

    assert result["queries"]
    assert result["inferred_domain"] in {"survey", "saas", "data analysis"}
    joined = " ".join(result["queries"]).lower()
    assert "common pitfalls" in joined
    assert "missing data" in joined
    assert "churn" in joined or "satisfaction" in joined


def test_parse_reddit_search_labels_findings_as_weak_community_evidence():
    payload = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "Common churn modeling mistakes",
                        "permalink": "/r/datascience/comments/abc/common_churn_modeling_mistakes/",
                        "selftext": "Beware leakage from post-cancel fields.",
                        "subreddit": "datascience",
                        "author": "analyst",
                        "score": 42,
                        "num_comments": 7,
                        "created_utc": 1_700_000_000,
                    }
                }
            ]
        }
    }

    findings = parse_reddit_search(payload, query="customer churn common pitfalls")

    assert len(findings) == 1
    finding = findings[0]
    assert finding["source"] == "reddit"
    assert finding["source_type"] == "community_discussion"
    assert finding["evidence_level"] == "weak"
    assert finding["url"].startswith("https://www.reddit.com/")
    assert "unverified" in finding["tags"]


@pytest.mark.asyncio
async def test_search_reddit_persists_mocked_findings(monkeypatch, survey_dataset):
    async def fake_search_reddit(**kwargs):
        return [
            {
                "query": kwargs["query"],
                "source": "reddit",
                "source_type": "community_discussion",
                "evidence_level": "weak",
                "title": "Survey data quality issue",
                "url": "https://www.reddit.com/r/analytics/comments/1/survey/",
                "snippet": "NPS comments can be biased toward extreme respondents.",
                "tags": ["community_signal", "unverified"],
                "accepted_for_okf": False,
            }
        ]

    monkeypatch.setattr("dataclaw_context_research.tools.search_reddit", fake_search_reddit)

    result = await context_research_search_reddit(
        query="customer survey nps bias",
        dataset_id=survey_dataset["id"],
        problem_statement="Understand churn from survey responses",
    )

    assert result["status"] == "saved"
    assert result["saved_count"] == 1
    findings = filter_findings(dataset_id=survey_dataset["id"])
    assert len(findings) == 1
    assert findings[0]["problem_statement"] == "Understand churn from survey responses"


@pytest.mark.asyncio
async def test_summarize_and_save_findings_to_okf(monkeypatch, survey_dataset):
    async def fake_search_reddit(**kwargs):
        return [
            {
                "query": kwargs["query"],
                "source": "reddit",
                "source_type": "community_discussion",
                "evidence_level": "weak",
                "title": "Churn leakage warning",
                "url": "https://www.reddit.com/r/datascience/comments/2/churn/",
                "snippet": "Watch for leakage from fields created after cancellation.",
                "tags": ["community_signal", "unverified"],
                "accepted_for_okf": False,
            }
        ]

    monkeypatch.setattr("dataclaw_context_research.tools.search_reddit", fake_search_reddit)
    await context_research_search_reddit(query="churn leakage pitfalls", dataset_id=survey_dataset["id"])

    summary = await context_research_summarize_findings(dataset_id=survey_dataset["id"])
    assert summary["count"] == 1
    assert summary["evidence_levels"]["weak"] == 1
    assert summary["caveats"]

    bundle = generate_bundle(survey_dataset["id"])
    saved = await context_research_save_to_okf(bundle_id=bundle["id"], dataset_id=survey_dataset["id"])
    assert saved["saved_findings"] == 1

    external_context = Path(bundle["path"]) / "notes" / "external_context.md"
    text = external_context.read_text(encoding="utf-8")
    assert "External Context" in text
    assert "weak" in text
    assert "Churn leakage warning" in text
    assert read_findings()[0]["accepted_for_okf"] is True


@pytest.mark.asyncio
async def test_list_findings_empty():
    result = await context_research_list_findings()
    assert result == {"findings": [], "count": 0}
