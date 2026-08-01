import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "skill-library" / "causal_inference.md"
MIRROR = ROOT / "openclaw-plugins" / "dataclaw" / "skills" / "causal_inference" / "SKILL.md"


def _read():
    text = CANONICAL.read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    return yaml.safe_load(frontmatter), body, text


def test_causal_inference_contract_mirror_and_routing():
    meta, body, text = _read()
    assert set(meta) == {"name", "description", "tags"}
    assert meta["name"] == "causal_inference"
    assert "inside the Dataclaw data-science workflow" in meta["description"]
    assert "Use for " in meta["description"]
    assert next(line for line in body.splitlines() if line.strip()).startswith("**Related skills:**")
    assert MIRROR.read_text(encoding="utf-8") == text
    router = (ROOT / "skill-library" / "dataclaw.md").read_text(encoding="utf-8")
    assert "`causal_inference` for cause-and-effect questions" in router


def test_causal_inference_pins_identification_guardrails():
    _, body, _ = _read()
    for phrase in (
        "no design identifies the effect",
        "Staggered-adoption DiD",
        "does not use already-treated units as untreated controls",
        "Require common support",
        "Cross-fit flexible nuisance models",
        "Treat mediation as a separate identification problem",
        "below a default 5 units",
        "complementary suppression",
        "Never recommend consequential action",
    ):
        assert phrase in body
    assert not re.findall(r"`causal_[a-z_]+`", body)
