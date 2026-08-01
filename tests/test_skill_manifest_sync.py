"""Parity check: skills mirrored into the openclaw plugin must match canonical.

``skill-library/`` is the canonical, browsable install library served by the
dataclaw API. The openclaw plugin ships a *subset* of those skills in its own
``skills/`` directory (loaded via ``openclaw.plugin.json``). The two are
hand-maintained duplicates with no build-time sync, so this test fails loudly
when a mirrored copy drifts from its canonical source.

The check is intentionally one-directional: everything the plugin ships must
match canonical, but the plugin is allowed to ship only a subset (it does not
have to mirror every library skill).
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LIBRARY_DIR = REPO_ROOT / "skill-library"
PLUGIN_SKILLS_DIR = REPO_ROOT / "openclaw-plugins" / "dataclaw" / "skills"


def _mirrored_skill_dirs() -> list[Path]:
    if not PLUGIN_SKILLS_DIR.is_dir():
        return []
    return sorted(p for p in PLUGIN_SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file())


MIRRORED = _mirrored_skill_dirs()


def test_plugin_ships_at_least_one_mirrored_skill():
    """Guard so the parametrized parity test can't pass vacuously if discovery breaks."""
    assert MIRRORED, f"No SKILL.md files discovered under {PLUGIN_SKILLS_DIR}"


@pytest.mark.parametrize("skill_dir", MIRRORED, ids=lambda p: p.name)
def test_mirrored_skill_matches_canonical(skill_dir: Path):
    name = skill_dir.name
    canonical = LIBRARY_DIR / f"{name}.md"
    installed = skill_dir / "SKILL.md"

    assert canonical.is_file(), (
        f"Plugin ships skill '{name}' but there is no canonical "
        f"skill-library/{name}.md. Add the canonical copy or remove the plugin copy."
    )

    canonical_text = canonical.read_text(encoding="utf-8")
    installed_text = installed.read_text(encoding="utf-8")
    assert installed_text == canonical_text, (
        f"Skill '{name}' has drifted between its two locations.\n"
        f"  canonical: {canonical.relative_to(REPO_ROOT)}\n"
        f"  plugin:    {installed.relative_to(REPO_ROOT)}\n"
        f"Re-sync by copying the canonical file over the plugin copy."
    )
