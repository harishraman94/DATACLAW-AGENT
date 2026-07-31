"""Tests for config resolution."""

import json
import pytest

from dataclaw.config.paths import DATACLAW_HOME, config_path, sessions_dir, skills_dir
from dataclaw.config.migrations import migrate_runtime_utility_config
from dataclaw.config.resolver import (
    invalidate_cache,
    resolve,
    resolve_agent_runtime,
    resolve_bool,
    resolve_utility_backend,
)
from dataclaw.config.schema import DataclawConfig


def test_dataclaw_home_from_env(tmp_dataclaw_home):
    """DATACLAW_HOME should point to temp dir in tests."""
    assert tmp_dataclaw_home.exists()


def test_default_config():
    config = DataclawConfig()
    assert config.agent.runtime == "openclaw"
    assert config.llm.backend == "codex"
    assert config.compaction.enabled is False
    assert config.app.max_turns == 30
    assert config.app.host == "127.0.0.1"


def test_resolve_default():
    invalidate_cache()
    result = resolve("nonexistent.key", "NONEXISTENT_ENV_VAR", "default_value")
    assert result == "default_value"


def test_resolve_env_var(monkeypatch):
    monkeypatch.setenv("TEST_RESOLVE_VAR", "from_env")
    result = resolve("some.path", "TEST_RESOLVE_VAR", "default")
    assert result == "from_env"


def test_resolve_config_file(tmp_dataclaw_home):
    invalidate_cache()
    config_file = tmp_dataclaw_home / "dataclaw.config.json"
    config_file.write_text(json.dumps({"llm": {"backend": "openai"}}))

    # Need to patch config_path to point to our temp dir
    import dataclaw.config.resolver as resolver
    import dataclaw.config.paths as paths
    original_config_path = paths.config_path

    try:
        paths.config_path = lambda: config_file
        invalidate_cache()
        result = resolve("llm.backend", "NONEXISTENT", "anthropic")
        assert result == "openai"
    finally:
        paths.config_path = original_config_path
        invalidate_cache()


def test_resolve_bool_true(monkeypatch):
    monkeypatch.setenv("TEST_BOOL", "true")
    assert resolve_bool("x", "TEST_BOOL") is True


def test_resolve_bool_false(monkeypatch):
    monkeypatch.setenv("TEST_BOOL", "false")
    assert resolve_bool("x", "TEST_BOOL") is False


def test_resolve_bool_default():
    assert resolve_bool("nonexistent", "NONEXISTENT", default=True) is True


def test_migrate_hermes_runtime_and_utility_model() -> None:
    raw = {
        "llm": {
            "backend": "hermes",
            "codex": {"model": "old-model"},
        },
        "plugins": {
            "hermes": {
                "utility_backend": "codex",
                "utility_model": "gpt-5.5",
            }
        },
    }

    assert migrate_runtime_utility_config(raw) is True
    assert raw["agent"]["runtime"] == "hermes"
    assert raw["llm"]["backend"] == "codex"
    assert raw["llm"]["codex"]["model"] == "gpt-5.5"
    assert "utility_backend" not in raw["plugins"]["hermes"]
    assert "utility_model" not in raw["plugins"]["hermes"]


def test_migrate_direct_backend_to_dataclaw_runtime() -> None:
    raw = {"llm": {"backend": "anthropic"}}

    assert migrate_runtime_utility_config(raw) is True
    assert raw["agent"]["runtime"] == "dataclaw"
    assert raw["llm"]["backend"] == "anthropic"


def test_resolve_separate_runtime_and_utility(
    tmp_dataclaw_home,
    monkeypatch,
) -> None:
    config_file = tmp_dataclaw_home / "dataclaw.config.json"
    config_file.write_text(
        json.dumps(
            {
                "agent": {"runtime": "openclaw"},
                "llm": {"backend": "gemini"},
            }
        )
    )
    import dataclaw.config.paths as paths

    monkeypatch.setattr(paths, "config_path", lambda: config_file)
    invalidate_cache()
    try:
        assert resolve_agent_runtime() == "openclaw"
        assert resolve_utility_backend() == "gemini"
    finally:
        invalidate_cache()
