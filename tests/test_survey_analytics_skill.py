import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_LIBRARY = ROOT / "skill-library"
CANONICAL = SKILL_LIBRARY / "survey_analytics.md"
BUNDLED = (
    ROOT
    / "openclaw-plugins"
    / "dataclaw"
    / "skills"
    / "survey_analytics"
    / "SKILL.md"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_survey_analytics_skill_is_parseable_and_compact():
    text = _read(CANONICAL)

    assert text.startswith("---")
    _, frontmatter, body = text.split("---", 2)
    meta = yaml.safe_load(frontmatter)
    compact_body = " ".join(body.split())

    # Frontmatter mirrors the forecasting method-skill convention (name, description, tags).
    assert meta["name"] == "survey_analytics"
    assert set(meta) == {"name", "description", "tags"}
    assert "method" in meta["tags"]
    assert "inside the Dataclaw data-science workflow" in meta["description"]
    assert "open-text" in meta["description"]
    # A deep method playbook like forecasting — bounded, not lean-to-basic.
    assert len(text.splitlines()) < 200
    assert "TODO" not in text

    # Procedural voice, real platform tools named inline (no meta-narration).
    assert "Follow this process:" in body
    assert "data_list_datasets" in body
    assert "dataclaw_data.get_dataframe" in body
    assert "propose_plan" in body
    assert "record_eda_finding" in body
    assert "report_design_report" in body
    assert "publish_artifact" in body

    # Tool-free and honest, exactly like the current forecasting skill: the
    # statistics run in the notebook with real libraries — no fictional
    # survey_* tools and no surveykit package.
    assert "There is no survey tool or plugin to call" in body
    assert "samplics" in body
    assert "TaylorEstimator" in body
    assert "surveykit" not in body
    assert not re.findall(r"`(survey_[a-z_]+)`", body)

    # Deep-skill skeleton: routing table + contracts + threats-to-validity.
    assert "## Method routing by question type" in body
    assert "## Weighting and variance contract" in body
    assert "## Open-text coding contract" in body
    assert "## Threats to validity" in body

    # Executable correctness rules and refusals survive.
    assert "never pass a replicate-weight column as the one analysis weight" in compact_body.lower()
    assert "independent-group tests" in compact_body
    assert "Block theme prevalence" in body
    assert "design effect" in compact_body
    assert "%promoters" in body or "promoters" in compact_body


def test_survey_analytics_skill_is_bundled_without_drift():
    assert BUNDLED.is_file()
    assert _read(BUNDLED) == _read(CANONICAL)


def test_core_skills_route_survey_work_with_explicit_precedence():
    dataclaw = _read(SKILL_LIBRARY / "dataclaw.md")
    structured_eda = _read(SKILL_LIBRARY / "structured_eda.md")

    assert "fetch `survey_analytics`" in dataclaw
    assert "`survey_analytics` governs survey-specific method" in dataclaw
    assert "fetch\nand follow `survey_analytics`" in structured_eda
    assert "`survey_analytics`\ngoverns survey-specific method" in structured_eda
