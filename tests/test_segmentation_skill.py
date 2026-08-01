import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_LIBRARY = ROOT / "skill-library"
CANONICAL = SKILL_LIBRARY / "segmentation.md"
OPENCLAW = (
    ROOT
    / "openclaw-plugins"
    / "dataclaw"
    / "skills"
    / "segmentation"
    / "SKILL.md"
)


def _parse_skill(path: Path) -> tuple[dict, str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter), body.strip(), text


def test_segmentation_skill_follows_dataclaw_authoring_contract():
    meta, body, text = _parse_skill(CANONICAL)

    # Frontmatter mirrors the forecasting / survey_analytics method-skill convention.
    assert meta["name"] == CANONICAL.stem == OPENCLAW.parent.name == "segmentation"
    assert set(meta) == {"name", "description", "tags"}
    assert "inside the Dataclaw data-science workflow" in meta["description"]
    assert "Use for " in meta["description"]
    assert "uplift" in meta["description"]
    assert "method" in meta["tags"]
    assert "segmentation" in meta["tags"]

    first_body_line = next(line for line in body.splitlines() if line.strip())
    assert first_body_line.startswith("**Related skills:**")
    # A deep method playbook like forecasting — bounded, not lean-to-basic.
    assert len(text.splitlines()) < 200
    assert len(body.splitlines()) < 500
    assert len(body.split()) < 5_000
    assert "TODO" not in text
    assert text.endswith("\n")


def test_segmentation_skill_matches_openclaw_mirror():
    assert OPENCLAW.read_text(encoding="utf-8") == CANONICAL.read_text(
        encoding="utf-8"
    )


def test_segmentation_skill_reuses_the_governed_workflow_by_exact_tool_names():
    """Segmentation is a numbered flow over the `dataclaw_data_science` workflow
    that reuses the governed tools and sibling method skills by their exact
    names — it does not stand up a parallel segmentation system."""
    _, body, _ = _parse_skill(CANONICAL)

    assert "Follow this process:" in body

    required_phrases = [
        "runs inside the `dataclaw_data_science` workflow",
        "There is no segmentation tool or plugin to call",
        "the statistics run in the notebook with standard libraries",
        "`dataclaw_data_list_datasets`",
        "`dataclaw_open_notebook`",
        "`dataclaw_data.get_dataframe",
        "Fetch `structured_eda`",
        "`dataclaw_record_eda_finding`",
        "`dataclaw_summarize_eda_readiness`",
        "`dataclaw_propose_plan`",
        "`dataclaw_update_plan`",
        "`feature_engineering`",
        "`survey_analytics`",
        "`predictive_modeling`",
        "`causal_inference`",
        "`dataclaw_query_mlflow_runs`",
        "`dataclaw_request_analysis_review`",
        "`dataclaw_get_review_gate`",
        "`analysis_review` gate",
        "`visualization`",
        "`report_design_report` and `report_publish`",
        "`publish_artifact`",
    ]
    for phrase in required_phrases:
        assert phrase in body, f"missing reuse phrase: {phrase!r}"


def test_segmentation_skill_invents_no_segmentation_tools_or_library():
    """Regression guard mirroring the forecasting skill: the method must be
    expressed as reuse + real notebook libraries only, with no fabricated
    `segmentkit`/`clusterkit` package and no `segment_*` MCP tool surface."""
    _, body, _ = _parse_skill(CANONICAL)

    assert "segmentkit" not in body
    assert "clusterkit" not in body
    fabricated = re.findall(r"`(segment_[a-z_]+)`", body)
    assert not fabricated, f"fabricated segment_* tool names present: {fabricated}"

    # Only real, existing libraries are named for the notebook statistics.
    for lib in ("scikit-learn", "hdbscan", "kmodes", "gower", "prince", "stepmix"):
        assert lib in body, f"expected real library named: {lib!r}"


def test_segmentation_skill_has_the_deep_method_skeleton():
    _, body, _ = _parse_skill(CANONICAL)

    for heading in (
        "## Segmentation type by decision",
        "## Clustering method by data shape",
        "## Validation and stability contract",
        "## Actionability contract",
        "## Threats to validity",
        "## Domain controls",
    ):
        assert heading in body, f"missing section: {heading!r}"


def test_segmentation_skill_encodes_statistical_and_decision_guardrails():
    _, body, _ = _parse_skill(CANONICAL)
    compact = " ".join(body.split())

    required_phrases = [
        # Failure mode 1: clusters from noise — tendency + stability before belief.
        "Test **cluster tendency**",
        "Hopkins",
        # Hopkins direction is implementation-dependent; the skill must be
        # convention-independent, never a bare inverted threshold.
        "toward the clustered pole",
        "fpc::clusterboot",
        "indistinguishable from noise",
        # Failure mode 2: wrong construct for the decision.
        "do not cluster to rediscover a variable you already have",
        "never target by outcome level",
        "persuadables from sure-things and sleeping-dogs",
        # Measurement-level correctness.
        "never one-hot categoricals into k-means",
        # Direct identifiers and PII never enter the feature matrix or profiles.
        "exclude names, email addresses, phone numbers",
        "join keys from the feature matrix and model-visible profiles",
        # Density clustering treats noise honestly.
        "Noise is a legitimate class",
        "HDBSCAN noise is coverage, not a cluster",
        "silhouette undefined: fewer than two non-noise clusters",
        # Actionability / operationalization.
        "typing/assignment model",
        "substantial",
        "differentiable",
        "actionable",
        # Fairness.
        "Proxy discrimination",
        # Suppression floor is defined (default value + complementary), not just mandated.
        "fewer than a default 5 members",
        "complementary suppression",
    ]
    for phrase in required_phrases:
        assert phrase in compact or phrase in body, f"missing guardrail phrase: {phrase!r}"

    # Regression guard: the inverted bare Hopkins threshold must never reappear.
    assert "well below 0.5" not in body


def test_core_skills_route_segmentation_work():
    dataclaw = (SKILL_LIBRARY / "dataclaw.md").read_text(encoding="utf-8")
    structured_eda = (SKILL_LIBRARY / "structured_eda.md").read_text(encoding="utf-8")
    survey = (SKILL_LIBRARY / "survey_analytics.md").read_text(encoding="utf-8")

    assert "`segmentation` for dividing a population into segments" in dataclaw
    assert "`predictive_modeling`, `segmentation`, `feature_engineering`" in dataclaw
    assert "fetch `segmentation` before proposing the clustering approach" in structured_eda
    assert "`segmentation`" in survey
