import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skill-library" / "forecasting.md"
OPENCLAW = (
    ROOT
    / "openclaw-plugins"
    / "dataclaw"
    / "skills"
    / "forecasting"
    / "SKILL.md"
)


def _parse_skill(path: Path) -> tuple[dict, str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter), body.strip(), text


def test_forecasting_skill_follows_dataclaw_authoring_contract():
    meta, body, text = _parse_skill(CANONICAL)

    assert meta["name"] == CANONICAL.stem == OPENCLAW.parent.name
    assert set(meta) == {"name", "description", "tags"}
    assert "Use for " in meta["description"]
    assert "time-series forecasts" in meta["description"]
    assert "scenario planning" in meta["description"]
    assert "forecasting" in meta["tags"]

    first_body_line = next(line for line in body.splitlines() if line.strip())
    assert first_body_line.startswith("**Related skills:**")
    assert len(body.splitlines()) < 500
    assert len(body.split()) < 5_000
    assert text.endswith("\n")


def test_forecasting_skill_matches_openclaw_mirror():
    assert OPENCLAW.read_text(encoding="utf-8") == CANONICAL.read_text(
        encoding="utf-8"
    )


def test_forecasting_skill_is_a_numbered_flow_over_the_dataclaw_workflow():
    """Forecasting mirrors the `dataclaw_data_science` skill: a numbered,
    imperative process that reuses the governed workflow tools by their exact
    names — it does not stand up a parallel forecasting system."""
    _, body, _ = _parse_skill(CANONICAL)

    assert "Follow this process:" in body

    required_phrases = [
        "runs inside the `dataclaw_data_science` workflow",
        "There is no forecasting tool or plugin to call",
        "the statistics run in the notebook with standard libraries",
        "`dataclaw_data_list_datasets`",
        "`dataclaw_open_notebook`",
        "Fetch `structured_eda`",
        "`dataclaw_record_eda_finding`",
        "`dataclaw_summarize_eda_readiness`",
        "`dataclaw_propose_plan`",
        "`dataclaw_update_plan`",
        "`feature_engineering`",
        "`dataclaw_query_mlflow_runs`",
        "`dataclaw_request_analysis_review`",
        "`analysis_review` gate",
        "`visualization`",
        "`report_design_report` and `report_publish`",
        "`publish_artifact`",
    ]

    for phrase in required_phrases:
        assert phrase in body, f"missing reuse phrase: {phrase!r}"


def test_forecasting_skill_invents_no_forecast_tools_or_library():
    """Regression guard: earlier drafts fabricated a `forecastkit` library and a
    surface of `forecast_*` MCP tools that exist nowhere in the codebase. The
    method must be expressed as reuse + notebook code only."""
    _, body, _ = _parse_skill(CANONICAL)

    assert "forecastkit" not in body
    fabricated = re.findall(r"forecast_[a-z]+", body)
    assert not fabricated, f"fabricated forecast_* tool names present: {fabricated}"


def test_forecasting_skill_encodes_statistical_guardrails():
    _, body, _ = _parse_skill(CANONICAL)

    required_phrases = [
        "ADI ≥ 1.32 or CV² ≥ 0.49",
        "compare with MASE only",
        "Do not use plain SARIMA",
        "Require ≥2 seasonal cycles",
        "about 30 observations for ARIMA",
        "each foundation model’s context window",
        "public-benchmark contamination risk",
        "Use rolling-origin backtesting only",
        "Set these from the EDA",
        "below 6 origins",
        "at least 10 origins",
        "below about 30 origin × horizon observations",
        "Harvey-Leybourne-Newbold",
        "champion versus the configured naive baseline and runner-up",
        "MCB/Nemenyi-style comparisons",
        "Ljung-Box",
        "Require explicit user acceptance to generate a candidate that lost to naive",
        "best admissible regressor-capable candidate",
        "revealed metadata",
        "headline caveats",
    ]

    for phrase in required_phrases:
        assert phrase in body, f"missing guardrail phrase: {phrase!r}"
