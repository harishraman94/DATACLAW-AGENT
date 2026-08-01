"""Tests for skill providers."""

import asyncio

import pytest

from dataclaw.providers.skill.implementations.file_skill import FileSkillProvider


@pytest.fixture
def skill_dir(tmp_dataclaw_home):
    sdir = tmp_dataclaw_home / "skills"
    sdir.mkdir(exist_ok=True)
    return sdir


@pytest.fixture
def provider(skill_dir):
    return FileSkillProvider(directory=skill_dir)


def _write_skill(skill_dir, name, meta_yaml, body):
    path = skill_dir / f"{name}.md"
    path.write_text(f"---\n{meta_yaml}\n---\n\n{body}\n")


@pytest.fixture
def library_dir(tmp_path, monkeypatch):
    lib = tmp_path / "skill-library"
    lib.mkdir()
    import dataclaw.storage.skill_library as mod
    monkeypatch.setattr(mod, "skill_library_dir", lambda: lib)
    return lib


def _write_library_skill(library_dir, name, meta_yaml, body):
    path = library_dir / f"{name}.md"
    path.write_text(f"---\n{meta_yaml}\n---\n\n{body}\n")


@pytest.mark.asyncio
async def test_resolve_empty(provider):
    result = await provider.resolve_skills({"messages": []})
    assert result == []


@pytest.mark.asyncio
async def test_resolve_skills(provider, skill_dir):
    _write_skill(skill_dir, "profiling", "name: profiling\ndescription: Profile data", "Step 1: Load data")
    result = await provider.resolve_skills({"messages": []})
    assert len(result) == 1
    assert result[0]["id"] == "profiling"
    assert result[0]["name"] == "profiling"


@pytest.mark.asyncio
async def test_format_for_prompt(provider, skill_dir):
    _write_skill(skill_dir, "test", "name: test\ndescription: A test skill", "Do the thing")
    skills = await provider.resolve_skills({"messages": []})
    fragments = await provider.format_for_prompt(skills)
    assert len(fragments) == 1
    assert "test" in fragments[0]


@pytest.mark.asyncio
async def test_fetch_skill(provider, skill_dir):
    _write_skill(skill_dir, "my_skill", "name: my_skill", "Content here")
    result = await provider.fetch_skill("my_skill")
    assert result is not None
    assert result["id"] == "my_skill"


@pytest.mark.asyncio
async def test_fetch_nonexistent(provider):
    result = await provider.fetch_skill("nonexistent")
    assert result == {"content": "Skill not found: nonexistent", "is_error": True}


@pytest.mark.asyncio
async def test_fetch_uninstalled_library_skill_is_rejected(provider, library_dir):
    _write_library_skill(
        library_dir,
        "report_design",
        "name: report_design\ndescription: Report design",
        "Call report_design_report for final reports",
    )

    await provider.resolve_skills({"messages": []})
    result = await provider.fetch_skill("report_design")

    assert result == {
        "content": "Skill not found: report_design",
        "is_error": True,
    }


@pytest.mark.asyncio
async def test_resolved_skills_are_isolated_between_concurrent_requests(
    provider, skill_dir, monkeypatch
):
    _write_skill(skill_dir, "alpha", "name: alpha", "Alpha instructions")
    _write_skill(skill_dir, "beta", "name: beta", "Beta instructions")
    monkeypatch.setattr(
        provider,
        "_resolve_allowed_ids",
        lambda state: list(state["allowed"]),
    )
    alpha_resolved = asyncio.Event()
    beta_resolved = asyncio.Event()

    async def alpha_request():
        await provider.resolve_skills({"allowed": ["alpha"]})
        alpha_resolved.set()
        await beta_resolved.wait()
        return await provider.fetch_skill("skill_1")

    async def beta_request():
        await alpha_resolved.wait()
        await provider.resolve_skills({"allowed": ["beta"]})
        beta_resolved.set()
        return await provider.fetch_skill("skill_1")

    alpha, beta = await asyncio.gather(alpha_request(), beta_request())

    assert alpha["skill_id"] == "alpha"
    assert alpha["name"] == "alpha"
    assert beta["skill_id"] == "beta"
    assert beta["name"] == "beta"


@pytest.mark.asyncio
async def test_stale_library_skill_is_warned_in_prompt_and_fetch(provider, skill_dir, library_dir):
    _write_library_skill(library_dir, "visualization", "name: visualization", "new instructions")
    _write_skill(
        skill_dir,
        "visualization",
        "name: visualization\ndescription: Viz\nsource: library\nlibrary_id: visualization",
        "old instructions",
    )

    skills = await provider.resolve_skills({"messages": []})
    assert skills[0]["installed_stale"] is True

    fragments = await provider.format_for_prompt(skills)
    assert "Skill freshness warning" in fragments[0]
    assert "stale installed library copy" in fragments[0]

    fetched = await provider.fetch_skill("visualization")
    assert fetched["installed_stale"] is True
    assert fetched["installed"] is True
    assert fetched["source"] == "installed"
    assert fetched["origin"] == "library"
    assert "Skill freshness warning" in fetched["content"]
    assert "installed copy below remains the active source" in fetched["content"]
    assert "old instructions" in fetched["content"]
    assert "new instructions" not in fetched["content"]


@pytest.mark.asyncio
async def test_missing_session_skill_resolution_fails_closed(provider, skill_dir):
    _write_skill(skill_dir, "private", "name: private", "Private instructions")

    skills = await provider.resolve_skills({
        "session_id": "session-does-not-exist",
        "messages": [],
    })
    fetched = await provider.fetch_skill("private")

    assert skills == []
    assert fetched["is_error"] is True
