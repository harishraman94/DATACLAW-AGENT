"""Tests for the default tool availability registry — focused on
``seed_plugin_defaults`` and the ``seeded_plugins`` one-shot semantics."""

from __future__ import annotations

from dataclaw.providers.tool.implementations.registry import DefaultToolAvailability
from dataclaw.providers.tool.tool_config import (
    ProjectToolConfig,
    load_global_tool_config,
    save_global_tool_config,
    ToolConfig,
)


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.definition = {"name": name}

    async def execute(self, **_: object) -> dict[str, object]:
        return {}


def test_seed_plugin_defaults_disables_listed_tools_first_time() -> None:
    reg = DefaultToolAvailability()
    reg.register_tool(_FakeTool("foo_a"))
    reg.register_tool(_FakeTool("foo_b"))

    reg.seed_plugin_defaults("plugin-foo", ["foo_a", "foo_b"])

    cfg = load_global_tool_config()
    assert cfg.disabled == {"foo_a", "foo_b"}
    assert "plugin-foo" in cfg.seeded_plugins


def test_seed_plugin_defaults_is_one_shot_per_plugin() -> None:
    reg = DefaultToolAvailability()
    reg.register_tool(_FakeTool("foo_a"))
    reg.seed_plugin_defaults("plugin-foo", ["foo_a"])

    # User re-enables foo_a via UI.
    reg.set_tool_enabled("foo_a", True)
    assert "foo_a" not in load_global_tool_config().disabled

    # Plugin reloads and re-seeds — the user's enable must stick.
    reg2 = DefaultToolAvailability()
    reg2.register_tool(_FakeTool("foo_a"))
    reg2.seed_plugin_defaults("plugin-foo", ["foo_a"])

    assert "foo_a" not in load_global_tool_config().disabled


def test_seed_plugin_defaults_persists_seeded_marker_even_with_no_changes() -> None:
    # Pre-existing config: foo_a already manually disabled by the user before
    # the plugin's first load. Seeding adds nothing new to `disabled` but must
    # still mark the plugin id as seeded so we don't re-seed next time.
    initial = ToolConfig(disabled={"foo_a"})
    save_global_tool_config(initial)

    reg = DefaultToolAvailability()
    reg.register_tool(_FakeTool("foo_a"))
    reg.seed_plugin_defaults("plugin-foo", ["foo_a"])

    cfg = load_global_tool_config()
    assert "plugin-foo" in cfg.seeded_plugins


def test_seed_plugin_defaults_ignores_empty_inputs() -> None:
    reg = DefaultToolAvailability()
    reg.seed_plugin_defaults("", ["foo_a"])
    reg.seed_plugin_defaults("plugin-foo", ["", "foo_a"])

    cfg = load_global_tool_config()
    assert cfg.disabled == {"foo_a"}
    assert cfg.seeded_plugins == {"plugin-foo"}


def test_registration_source_marks_plugin_tools() -> None:
    reg = DefaultToolAvailability()

    with reg.registration_source("plugin:artifacts"):
        reg.register_tool(_FakeTool("publish_artifact"))

    assert reg.get_all_tools_with_status()[0]["source"] == "plugin:artifacts"


def test_startup_registration_does_not_bump_persistent_version() -> None:
    reg = DefaultToolAvailability()
    initial_version = reg.version

    reg.register_tool(_FakeTool("startup_tool"))
    assert reg.version == initial_version

    reg.finalize_registration()
    reg.register_tool(_FakeTool("runtime_tool"))
    assert reg.version == initial_version + 1


def test_tool_listing_applies_session_overrides(monkeypatch) -> None:
    import dataclaw.providers.tool.implementations.registry as registry_module

    reg = DefaultToolAvailability()
    reg.register_tool(_FakeTool("globally_off"))
    reg.register_tool(_FakeTool("session_off"))
    reg._tool_config.disabled.update({"globally_off"})
    monkeypatch.setattr(
        registry_module,
        "_load_session_data",
        lambda _session_id: {
            "toolConfig": {
                "enabled": ["globally_off"],
                "disabled": ["session_off"],
            }
        },
    )

    statuses = {
        tool["name"]: tool["enabled"]
        for tool in reg.get_all_tools_with_status(session_id="session-1")
    }

    assert statuses == {"globally_off": True, "session_off": False}


def test_tool_listing_marks_tools_outside_session_scope_disabled(monkeypatch) -> None:
    import dataclaw.providers.tool.implementations.registry as registry_module

    reg = DefaultToolAvailability()
    reg.register_tool(_FakeTool("selected"))
    reg.register_tool(_FakeTool("outside_scope"))
    monkeypatch.setattr(
        registry_module,
        "_load_session_data",
        lambda _session_id: {"toolIds": ["selected"]},
    )

    listed = {
        tool["name"]: (tool["enabled"], tool["in_scope"])
        for tool in reg.get_all_tools_with_status(session_id="session-1")
    }

    assert listed == {
        "selected": (True, True),
        "outside_scope": (False, False),
    }


async def test_resolve_tools_applies_overrides_inside_hard_scope(
    monkeypatch, tmp_path
) -> None:
    import dataclaw.providers.tool.implementations.registry as registry_module

    reg = DefaultToolAvailability()
    for name in ("session_enabled", "project_enabled", "outside_scope"):
        reg.register_tool(_FakeTool(name))
    reg._tool_config.disabled.update(
        {"session_enabled", "project_enabled", "outside_scope"}
    )
    monkeypatch.setattr(
        registry_module,
        "_load_session_data",
        lambda _session_id: {
            "toolIds": ["session_enabled", "project_enabled"],
            "toolConfig": {"enabled": ["session_enabled"]},
        },
    )
    monkeypatch.setattr(
        registry_module,
        "_resolve_project_dir",
        lambda _project_id: tmp_path,
    )
    monkeypatch.setattr(
        registry_module,
        "load_project_tool_config",
        lambda _path: ProjectToolConfig(enabled={"project_enabled"}),
    )

    definitions, callables = await reg.resolve_tools({
        "session_id": "session-1",
        "project_id": "project-1",
    })

    assert [definition["name"] for definition in definitions] == [
        "session_enabled",
        "project_enabled",
    ]
    assert set(callables) == {"session_enabled", "project_enabled"}


async def test_resolve_tools_fails_closed_for_missing_session(monkeypatch) -> None:
    import dataclaw.providers.tool.implementations.registry as registry_module

    reg = DefaultToolAvailability()
    reg.register_tool(_FakeTool("otherwise_enabled"))
    monkeypatch.setattr(
        registry_module,
        "_load_session_data",
        lambda _session_id: None,
    )

    definitions, callables = await reg.resolve_tools({
        "session_id": "missing-session",
    })

    assert definitions == []
    assert callables == {}
