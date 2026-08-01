import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skill-library" / "experiment_design.md"
MIRROR = ROOT / "openclaw-plugins" / "dataclaw" / "skills" / "experiment_design" / "SKILL.md"


def _read():
    text = CANONICAL.read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter), body, text


def test_experiment_design_contract_mirror_and_routing():
    meta, body, text = _read()
    assert set(meta) == {"name", "description", "tags"}
    assert "inside the Dataclaw data-science workflow" in meta["description"]
    assert "Use for " in meta["description"]
    assert next(line for line in body.splitlines() if line.strip()).startswith("**Related skills:**")
    assert MIRROR.read_text(encoding="utf-8") == text
    assert "`experiment_design` for A/B, cluster/geo, switchback, holdout, factorial, non-inferiority, or uplift experiments" in (
        ROOT / "skill-library" / "dataclaw.md"
    ).read_text(encoding="utf-8")


def test_experiment_design_pins_integrity_and_analysis_guardrails():
    _, body, _ = _read()
    for phrase in (
        "Never power on row count",
        "design effect",
        "row-level iid standard errors",
        "Check SRM against planned allocation",
        "Correct the declared comparison family",
        "Stop the confirmatory readout",
        "intention-to-treat first",
        "CUPED/ANCOVA only with pre-treatment covariates",
        "ordinary repeated p-values are invalid",
        "Low cluster count",
        "below a default 5 units",
        "complementary suppression",
    ):
        assert phrase in body
    assert not re.findall(r"`experiment_[a-z_]+`", body)
