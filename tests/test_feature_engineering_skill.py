import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skill-library" / "feature_engineering.md"
MIRROR = ROOT / "openclaw-plugins" / "dataclaw" / "skills" / "feature_engineering" / "SKILL.md"


def _read():
    text = CANONICAL.read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter), body, text


def test_feature_engineering_contract_mirror_and_routing():
    meta, body, text = _read()
    assert set(meta) == {"name", "description", "tags"}
    assert "inside the Dataclaw data-science workflow" in meta["description"]
    assert "Use for " in meta["description"]
    assert next(line for line in body.splitlines() if line.strip()).startswith("**Related skills:**")
    assert MIRROR.read_text(encoding="utf-8") == text
    router = (ROOT / "skill-library" / "dataclaw.md").read_text(encoding="utf-8")
    assert "fetch the `feature_engineering` skill" in router


def test_feature_engineering_pins_leakage_lineage_and_serving_guardrails():
    _, body, _ = _read()
    for phrase in (
        "ingestion/processing latency",
        "Keep names, emails, phone numbers",
        "Cross-fitted encoding",
        "Each row’s encoding excludes its own target",
        "test the serialized pipeline",
        "every output feature must map to source fields",
        "never impute across time from future observations",
        "below a default 5 units",
        "complementary suppression",
    ):
        assert phrase in body
    assert not re.findall(r"`feature_[a-z_]+`", body)
