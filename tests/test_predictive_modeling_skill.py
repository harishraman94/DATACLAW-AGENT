import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skill-library" / "predictive_modeling.md"
MIRROR = ROOT / "openclaw-plugins" / "dataclaw" / "skills" / "predictive_modeling" / "SKILL.md"


def _read():
    text = CANONICAL.read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter), body, text


def test_predictive_modeling_contract_mirror_and_routing():
    meta, body, text = _read()
    assert set(meta) == {"name", "description", "tags"}
    assert "inside the Dataclaw data-science workflow" in meta["description"]
    assert "Use for " in meta["description"]
    assert next(line for line in body.splitlines() if line.strip()).startswith("**Related skills:**")
    assert MIRROR.read_text(encoding="utf-8") == text
    assert "`predictive_modeling` for supervised prediction" in (
        ROOT / "skill-library" / "dataclaw.md"
    ).read_text(encoding="utf-8")


def test_predictive_modeling_pins_decision_and_deployment_guardrails():
    _, body, _ = _read()
    for phrase in (
        "error costs",
        "AUC alone never establishes operational value",
        "inside the training fold",
        "only inside training folds",
        "naive/business baseline",
        "Calibrate on held-out",
        "frozen final test",
        "Lock it before final test evaluation",
        "subgroup metrics with adequate uncertainty",
        "Feedback loops",
        "below a default 5 units",
        "complementary suppression",
        "Never auto-deploy",
    ):
        assert phrase in body
    assert not re.findall(r"`predict_[a-z_]+`", body)
