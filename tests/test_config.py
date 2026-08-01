"""Tests for config resolution."""

import json
import threading
from types import SimpleNamespace

import pytest

import dataclaw.api.routers.config as config_router
from dataclaw.api.routers.config import (
    _hot_reload_plugins,
    _mask_secrets_recursive,
    _strip_masked_secrets,
)
from dataclaw.config.paths import DATACLAW_HOME, config_path, sessions_dir, skills_dir
from dataclaw.config.resolver import resolve, resolve_bool, invalidate_cache
from dataclaw.config.schema import DataclawConfig


def test_dataclaw_home_from_env(tmp_dataclaw_home):
    """DATACLAW_HOME should point to temp dir in tests."""
    assert tmp_dataclaw_home.exists()


def test_default_config():
    config = DataclawConfig()
    assert config.llm.backend == "openclaw"
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


def test_kaggle_secrets_are_masked():
    config = {
        "plugins": {
            "kaggle": {
                "kaggle_api_token": "KGAT_abcdefghijklmnopqrstuvwxyz",
                "kaggle_key": "legacy-secret-value",
                "kaggle_username": "visible-user",
            },
        },
    }

    _mask_secrets_recursive(config)

    kaggle = config["plugins"]["kaggle"]
    assert kaggle["kaggle_api_token"] != "KGAT_abcdefghijklmnopqrstuvwxyz"
    assert kaggle["kaggle_key"] != "legacy-secret-value"
    assert kaggle["kaggle_username"] == "visible-user"


def test_masked_kaggle_secrets_are_not_written_back():
    updates = {
        "plugins": {
            "kaggle": {
                "kaggle_api_token": "KGAT_abc...wxyz",
                "kaggle_key": "***",
                "download_dir": "/tmp/kaggle",
            },
        },
    }

    _strip_masked_secrets(updates)

    kaggle = updates["plugins"]["kaggle"]
    assert "kaggle_api_token" not in kaggle
    assert "kaggle_key" not in kaggle
    assert kaggle["download_dir"] == "/tmp/kaggle"


def test_hot_reload_plugins_notifies_supported_plugins():
    observed = []

    class ReloadablePlugin:
        name = "reloadable"

        def on_config_update(self, config):
            observed.append(config)

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(plugins_list=[ReloadablePlugin(), object()])
        )
    )
    config = DataclawConfig(plugins={"kaggle": {"kaggle_api_token": "KGAT_new"}})

    _hot_reload_plugins(request, config)

    assert observed == [config]


@pytest.mark.asyncio
async def test_config_update_runs_plugin_reload_off_event_loop(
    monkeypatch,
):
    main_thread = threading.get_ident()
    callback_threads = []

    def fake_reload_plugins(request, config):
        callback_threads.append(threading.get_ident())

    monkeypatch.setattr(config_router, "_hot_reload_plugins", fake_reload_plugins)
    monkeypatch.setattr(config_router, "_hot_reload_agent", lambda request: None)
    monkeypatch.setattr(config_router, "_hot_reload_memory", lambda request: None)
    monkeypatch.setattr(config_router, "_hot_reload_compaction", lambda request: None)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                plugins_list=[],
                providers=SimpleNamespace(),
            )
        )
    )

    await config_router.update_config({}, request)

    assert callback_threads
    assert callback_threads[0] != main_thread
