"""Tests for the dataclaw-kaggle plugin."""

from __future__ import annotations

import os
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import dataclaw_kaggle as kaggle_plugin
from dataclaw_kaggle import registry, tools
from dataclaw_kaggle import client as kaggle_client
from dataclaw_kaggle.client import get_auth_config, get_config


# ── Registry tests ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def tmp_registry(tmp_path, monkeypatch):
    """Redirect the registry to a temp directory."""
    reg_path = tmp_path / "registry.json"
    monkeypatch.setattr(registry, "_registry_path", lambda: reg_path)
    return reg_path


def test_read_empty_registry():
    data = registry.read_registry()
    assert data == {"competitions": {}, "datasets": {}, "submissions": []}


def test_track_competition():
    entry = registry.track_competition("titanic", {"title": "Titanic", "reward": "$0"})
    assert entry["slug"] == "titanic"
    assert entry["title"] == "Titanic"
    assert "fetched_at" in entry

    # Verify persisted
    data = registry.read_registry()
    assert "titanic" in data["competitions"]


def test_track_competition_update():
    registry.track_competition("titanic", {"title": "Titanic"})
    entry = registry.track_competition("titanic", {"reward": "$10,000"})
    assert entry["title"] == "Titanic"
    assert entry["reward"] == "$10,000"


def test_get_competition():
    registry.track_competition("titanic", {"title": "Titanic"})
    assert registry.get_competition("titanic")["slug"] == "titanic"
    assert registry.get_competition("nonexistent") is None


def test_list_competitions():
    registry.track_competition("titanic", {"title": "Titanic"})
    registry.track_competition("house-prices", {"title": "House Prices"})
    comps = registry.list_competitions()
    assert len(comps) == 2


def test_track_dataset():
    entry = registry.track_dataset("user/dataset", {"title": "My Dataset"})
    assert entry["ref"] == "user/dataset"
    assert entry["title"] == "My Dataset"


def test_list_datasets():
    registry.track_dataset("user/ds1", {"title": "DS1"})
    registry.track_dataset("user/ds2", {"title": "DS2"})
    assert len(registry.list_datasets()) == 2


def test_record_download():
    registry.track_competition("titanic", {"title": "Titanic"})
    entry = registry.record_download(
        kind="competitions",
        key="titanic",
        download_path="/tmp/titanic",
        files=["train.csv", "test.csv"],
        dataclaw_dataset_id="abc123",
    )
    assert entry["downloaded"] is True
    assert entry["download_path"] == "/tmp/titanic"
    assert entry["files"] == ["train.csv", "test.csv"]
    assert entry["dataclaw_dataset_id"] == "abc123"


def test_delete_download():
    registry.track_competition("titanic", {"title": "Titanic"})
    registry.record_download("competitions", "titanic", "/tmp/titanic", ["train.csv"])
    assert registry.delete_download("competitions", "titanic")
    assert registry.get_competition("titanic") is None


def test_delete_download_nonexistent():
    assert registry.delete_download("competitions", "nonexistent") is False


def test_record_submission():
    entry = registry.record_submission(
        competition="titanic",
        file_path="/tmp/submission.csv",
        message="First attempt",
        result={"status": "submitted"},
    )
    assert entry["competition"] == "titanic"
    assert entry["id"].startswith("sub_")
    assert "submitted_at" in entry


def test_list_submissions():
    registry.record_submission("titanic", "/tmp/s1.csv", "Attempt 1")
    registry.record_submission("house-prices", "/tmp/s2.csv", "Attempt 1")
    registry.record_submission("titanic", "/tmp/s3.csv", "Attempt 2")

    all_subs = registry.list_submissions()
    assert len(all_subs) == 3

    titanic_subs = registry.list_submissions("titanic")
    assert len(titanic_subs) == 2


# ── Client config tests ────────────────────────────────────────────────────


def test_get_config_from_dict():
    u, k = get_config({"kaggle_username": "user1", "kaggle_key": "key1"})
    assert u == "user1"
    assert k == "key1"


def test_get_config_empty():
    u, k = get_config({})
    assert u == ""
    assert k == ""


def test_get_config_none_values():
    u, k = get_config({"kaggle_username": None, "kaggle_key": None})
    assert u == ""
    assert k == ""


def test_get_auth_config_modern_token():
    auth = get_auth_config({"kaggle_api_token": "KGAT_modern"})
    assert auth == {
        "username": "",
        "key": "",
        "api_token": "KGAT_modern",
    }


def test_get_auth_config_legacy_credentials():
    auth = get_auth_config({
        "kaggle_username": "legacy-user",
        "kaggle_key": "legacy-key",
    })
    assert auth == {
        "username": "legacy-user",
        "key": "legacy-key",
        "api_token": "",
    }


def test_get_auth_config_migrates_kgat_saved_as_legacy_key():
    auth = get_auth_config({
        "kaggle_username": "ignored-for-token-auth",
        "kaggle_key": "KGAT_existing-config",
    })
    assert auth == {
        "username": "ignored-for-token-auth",
        "key": "",
        "api_token": "KGAT_existing-config",
    }


def test_modern_token_is_scoped_to_client_creation(monkeypatch):
    kaggle_client.reset_api()
    monkeypatch.setenv("KAGGLE_USERNAME", "host-user")
    monkeypatch.setenv("KAGGLE_KEY", "host-key")
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    observed = {}

    class FakeApi:
        CONFIG_NAME_USER = "username"
        CONFIG_NAME_KEY = "key"
        CONFIG_NAME_TOKEN = "token"
        CONFIG_NAME_AUTH_METHOD = "auth_method"

        def __init__(self):
            observed.update({
                name: os.environ.get(name)
                for name in ("KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_API_TOKEN")
            })
            self.config_values = {}

    monkeypatch.setattr(kaggle_client, "_kaggle_api_cls", FakeApi)

    result = kaggle_client._get_api(
        username="configured-user",
        key="KGAT_configured-token",
    )

    assert observed == {
        "KAGGLE_USERNAME": "host-user",
        "KAGGLE_KEY": "host-key",
        "KAGGLE_API_TOKEN": None,
    }
    assert result.config_values == {
        "token": "KGAT_configured-token",
        "username": "configured-user",
        "auth_method": "ACCESS_TOKEN",
    }
    assert os.environ["KAGGLE_USERNAME"] == "host-user"
    assert os.environ["KAGGLE_KEY"] == "host-key"
    assert "KAGGLE_API_TOKEN" not in os.environ
    kaggle_client.reset_api()


def test_legacy_credentials_override_ambient_token_during_creation(monkeypatch):
    kaggle_client.reset_api()
    monkeypatch.setenv("KAGGLE_USERNAME", "host-user")
    monkeypatch.setenv("KAGGLE_KEY", "host-key")
    monkeypatch.setenv("KAGGLE_API_TOKEN", "host-token")
    observed = {}

    class FakeApi:
        CONFIG_NAME_USER = "username"
        CONFIG_NAME_KEY = "key"
        CONFIG_NAME_TOKEN = "token"
        CONFIG_NAME_AUTH_METHOD = "auth_method"

        def __init__(self):
            observed.update({
                name: os.environ.get(name)
                for name in ("KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_API_TOKEN")
            })
            self.config_values = {}

    monkeypatch.setattr(kaggle_client, "_kaggle_api_cls", FakeApi)

    result = kaggle_client._get_api(username="legacy-user", key="legacy-key")

    assert observed == {
        "KAGGLE_USERNAME": "host-user",
        "KAGGLE_KEY": "host-key",
        "KAGGLE_API_TOKEN": "host-token",
    }
    assert result.config_values == {
        "username": "legacy-user",
        "key": "legacy-key",
        "auth_method": "LEGACY_API_KEY",
    }
    assert os.environ["KAGGLE_USERNAME"] == "host-user"
    assert os.environ["KAGGLE_KEY"] == "host-key"
    assert os.environ["KAGGLE_API_TOKEN"] == "host-token"
    kaggle_client.reset_api()


def test_client_cache_refreshes_when_credentials_change(monkeypatch):
    kaggle_client.reset_api()
    created = []

    def fake_create_api(username, key, api_token):
        api = object()
        created.append((api, username, key, api_token))
        return api

    monkeypatch.setattr(kaggle_client, "_create_authenticated_api", fake_create_api)

    first = kaggle_client._get_api(api_token="KGAT_one")
    cached = kaggle_client._get_api(api_token="KGAT_one")
    second = kaggle_client._get_api(api_token="KGAT_two")

    assert cached is first
    assert second is not first
    assert len(created) == 2
    assert created[0][3] == "KGAT_one"
    assert created[1][3] == "KGAT_two"
    kaggle_client.reset_api()


def test_authentication_exit_becomes_runtime_error():
    class ExitingApi:
        def authenticate(self):
            raise SystemExit(1)

    with pytest.raises(RuntimeError, match="authentication is not configured"):
        kaggle_client._authenticate_api(ExitingApi())


def test_import_time_exit_becomes_runtime_error(monkeypatch):
    monkeypatch.setattr(kaggle_client, "_kaggle_api_cls", None)

    def exiting_import():
        raise SystemExit(1)

    monkeypatch.setattr(kaggle_client, "_import_kaggle_api_class", exiting_import)

    with pytest.raises(RuntimeError, match="initialize the Kaggle SDK"):
        kaggle_client._load_kaggle_api_class()


def test_safe_sdk_import_restores_host_environment(monkeypatch):
    monkeypatch.setattr(kaggle_client, "_kaggle_api_cls", None)
    monkeypatch.setenv("KAGGLE_USERNAME", "host-user")
    monkeypatch.setenv("KAGGLE_KEY", "host-key")
    monkeypatch.setenv("KAGGLE_API_TOKEN", "host-token")
    observed = {}
    fake_class = object()

    def fake_import():
        observed.update({
            name: os.environ.get(name)
            for name in ("KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_API_TOKEN")
        })
        return fake_class

    monkeypatch.setattr(kaggle_client, "_import_kaggle_api_class", fake_import)

    assert kaggle_client._load_kaggle_api_class() is fake_class
    assert observed == {
        "KAGGLE_USERNAME": "__dataclaw_import__",
        "KAGGLE_KEY": "__dataclaw_import__",
        "KAGGLE_API_TOKEN": None,
    }
    assert os.environ["KAGGLE_USERNAME"] == "host-user"
    assert os.environ["KAGGLE_KEY"] == "host-key"
    assert os.environ["KAGGLE_API_TOKEN"] == "host-token"


def test_plugin_token_never_enters_process_environment(monkeypatch):
    kaggle_client.reset_api()
    started = threading.Event()
    release = threading.Event()

    class SlowFakeApi:
        CONFIG_NAME_USER = "username"
        CONFIG_NAME_KEY = "key"
        CONFIG_NAME_TOKEN = "token"
        CONFIG_NAME_AUTH_METHOD = "auth_method"

        def __init__(self):
            self.config_values = {}
            started.set()
            assert release.wait(5)

    monkeypatch.setattr(kaggle_client, "_kaggle_api_cls", SlowFakeApi)
    worker = threading.Thread(
        target=lambda: kaggle_client._get_api(api_token="KGAT_review_sentinel")
    )
    worker.start()
    assert started.wait(5)
    assert os.environ.get("KAGGLE_API_TOKEN") != "KGAT_review_sentinel"
    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    kaggle_client.reset_api()


@pytest.mark.asyncio
async def test_run_kaggle_authenticates_and_calls_sdk_off_event_loop(monkeypatch):
    main_thread = threading.get_ident()
    observed_threads = []

    class FakeApi:
        def competitions_list(self, **kwargs):
            observed_threads.append(threading.get_ident())
            return kwargs["page"]

    def fake_get_api(username, key, api_token):
        observed_threads.append(threading.get_ident())
        assert api_token == "KGAT_worker"
        return FakeApi()

    monkeypatch.setattr(kaggle_client, "_get_api", fake_get_api)

    result = await kaggle_client.run_kaggle(
        "competitions_list",
        page=2,
        api_token="KGAT_worker",
    )

    assert result == 2
    assert observed_threads
    assert all(thread_id != main_thread for thread_id in observed_threads)


def test_plugin_config_update_refreshes_modules_and_client(monkeypatch):
    observed = {}
    monkeypatch.setattr(
        kaggle_plugin,
        "set_plugin_cfg",
        lambda cfg: observed.__setitem__("tools", cfg),
    )
    monkeypatch.setattr(
        kaggle_plugin,
        "set_router_cfg",
        lambda cfg: observed.__setitem__("router", cfg),
    )
    monkeypatch.setattr(
        kaggle_plugin,
        "reset_api",
        lambda: observed.__setitem__("reset", True),
    )
    monkeypatch.setattr(
        kaggle_plugin,
        "prepare_client",
        lambda: observed.__setitem__("prepared", True),
    )
    config = SimpleNamespace(plugins={"kaggle": {"kaggle_api_token": "KGAT_new"}})

    kaggle_plugin.KagglePlugin().on_config_update(config)

    assert observed == {
        "tools": {"kaggle_api_token": "KGAT_new"},
        "router": {"kaggle_api_token": "KGAT_new"},
        "reset": True,
        "prepared": True,
    }


def test_unconfigured_plugin_does_not_eagerly_import_sdk(monkeypatch):
    observed = {}
    monkeypatch.setattr(kaggle_plugin, "set_plugin_cfg", lambda cfg: None)
    monkeypatch.setattr(kaggle_plugin, "set_router_cfg", lambda cfg: None)
    monkeypatch.setattr(kaggle_plugin, "reset_api", lambda: None)
    monkeypatch.setattr(
        kaggle_plugin,
        "prepare_client",
        lambda: observed.__setitem__("prepared", True),
    )

    kaggle_plugin.KagglePlugin()._apply_config(
        SimpleNamespace(plugins={"kaggle": {}})
    )

    assert observed == {}


@pytest.mark.asyncio
async def test_download_hook_injects_trusted_session_context():
    state = {
        "session_id": "actual-session",
        "pending_tool_calls": [
            {
                "tool_name": "kaggle_download_competition",
                "tool_input": {
                    "competition": "titanic",
                    "session_id": "spoofed-session",
                },
            },
            {
                "tool_name": "kaggle_download_dataset",
                "tool_input": {
                    "dataset": "owner/data",
                    "dataclaw_session_id": "spoofed-session",
                },
            },
            {
                "tool_name": "kaggle_list_competitions",
                "tool_input": {"search": "housing"},
            },
        ],
    }

    updated = await kaggle_plugin.inject_kaggle_session_context(state)

    competition_input = updated["pending_tool_calls"][0]["tool_input"]
    assert "session_id" not in competition_input
    assert competition_input["dataclaw_session_id"] == "actual-session"
    assert updated["pending_tool_calls"][1]["tool_input"]["dataclaw_session_id"] == (
        "actual-session"
    )
    assert updated["pending_tool_calls"][2]["tool_input"] == {"search": "housing"}


def test_kaggle_secret_fields_use_password_inputs():
    fields = {
        field.name: field.field_type
        for field in kaggle_plugin.KagglePlugin().ui_manifest().config_fields
    }
    assert fields["kaggle_api_token"] == "secret"
    assert fields["kaggle_key"] == "secret"


def test_relative_download_root_is_anchored_to_plugin_data(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tools,
        "plugin_data_dir",
        lambda plugin_name: tmp_path / "plugins" / plugin_name,
    )
    monkeypatch.setattr(tools, "_plugin_cfg", {"download_dir": "downloads"})

    assert tools._download_root() == (
        tmp_path / "plugins" / "kaggle" / "downloads"
    ).resolve()


def test_competition_slug_cannot_escape_download_root(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "_download_root", lambda: tmp_path)

    with pytest.raises(ValueError, match="Invalid Kaggle competition slug"):
        tools._competition_dir("../../outside")


# ── Zip extraction tests ───────────────────────────────────────────────────


def _make_zip(zip_path: Path, members: dict[str, bytes]) -> None:
    """Helper: build a real zip at `zip_path` with the given member name → bytes."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def test_extract_zips_no_zip_files(tmp_path):
    (tmp_path / "train.csv").write_text("a,b\n1,2\n")
    extracted = tools._extract_zips_in_dir(tmp_path)
    assert extracted == []
    assert (tmp_path / "train.csv").is_file()


def test_extract_zips_single_zip(tmp_path):
    zip_path = tmp_path / "titanic.zip"
    _make_zip(zip_path, {"train.csv": b"a,b\n1,2\n", "test.csv": b"a,b\n3,4\n"})

    extracted = tools._extract_zips_in_dir(tmp_path)

    assert extracted == ["titanic.zip"]
    assert not zip_path.exists()
    assert (tmp_path / "train.csv").read_bytes() == b"a,b\n1,2\n"
    assert (tmp_path / "test.csv").read_bytes() == b"a,b\n3,4\n"


def test_extract_zips_multiple_zips(tmp_path):
    _make_zip(tmp_path / "first.zip", {"a.csv": b"a"})
    _make_zip(tmp_path / "second.zip", {"b.csv": b"b"})

    extracted = tools._extract_zips_in_dir(tmp_path)

    assert sorted(extracted) == ["first.zip", "second.zip"]
    assert not (tmp_path / "first.zip").exists()
    assert not (tmp_path / "second.zip").exists()
    assert (tmp_path / "a.csv").read_bytes() == b"a"
    assert (tmp_path / "b.csv").read_bytes() == b"b"


def test_extract_zips_corrupt_zip_skipped(tmp_path, caplog):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip file at all")
    _make_zip(tmp_path / "good.zip", {"ok.csv": b"ok"})

    with caplog.at_level("WARNING"):
        extracted = tools._extract_zips_in_dir(tmp_path)

    # Only the good zip is reported as extracted; bad.zip is left in place.
    assert extracted == ["good.zip"]
    assert bad.exists()
    assert (tmp_path / "ok.csv").read_bytes() == b"ok"
    assert any("bad.zip" in record.message for record in caplog.records)


def test_extract_zips_zip_slip_blocked(tmp_path, caplog):
    canary_target = tmp_path.parent / "evil.csv"
    if canary_target.exists():
        canary_target.unlink()
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    zip_path = work_dir / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.csv", b"pwned")
        zf.writestr("ok.csv", b"safe")

    with caplog.at_level("WARNING"):
        extracted = tools._extract_zips_in_dir(work_dir)

    assert extracted == ["evil.zip"]
    assert not canary_target.exists(), "zip-slip member must not escape destination"
    assert (work_dir / "ok.csv").read_bytes() == b"safe"
    assert any("path escape" in record.message for record in caplog.records)


def test_extract_zips_absolute_path_blocked(tmp_path, caplog):
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    zip_path = work_dir / "abs.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("/etc/evil.csv", b"pwned")
        zf.writestr("ok.csv", b"safe")

    with caplog.at_level("WARNING"):
        extracted = tools._extract_zips_in_dir(work_dir)

    assert extracted == ["abs.zip"]
    assert (work_dir / "ok.csv").read_bytes() == b"safe"
    # Make sure no absolute /etc/evil.csv was written (best-effort: ensure no
    # file named "evil.csv" anywhere under work_dir).
    assert not any(p.name == "evil.csv" for p in work_dir.rglob("*"))
    assert any("absolute-path" in record.message for record in caplog.records)


def test_extract_zips_missing_dir(tmp_path):
    missing = tmp_path / "does_not_exist"
    assert tools._extract_zips_in_dir(missing) == []


# ── Download integration tests ─────────────────────────────────────────────


@pytest.fixture
def kaggle_download_root(tmp_path, monkeypatch):
    """Redirect the Kaggle plugin's download root to a temp directory."""
    monkeypatch.setattr(tools, "_download_root", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def disable_dataclaw_register(monkeypatch):
    """Force-skip the dataclaw-data registration to avoid touching that module."""
    monkeypatch.setattr(tools, "_register_as_dataclaw_dataset", lambda **_: None)


def _drop_zip_into(dest_dir: Path, zip_name: str, members: dict[str, bytes]) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / zip_name
    _make_zip(zip_path, members)
    return zip_path


@pytest.mark.asyncio
async def test_download_competition_extracts_zip(
    kaggle_download_root, disable_dataclaw_register, monkeypatch
):
    """Mocked Kaggle SDK leaves a {slug}.zip; the tool should extract it."""

    async def fake_run_kaggle(method, *args, **kwargs):
        path = Path(kwargs["path"])
        _drop_zip_into(path, "titanic.zip", {"train.csv": b"a,b\n1,2\n", "test.csv": b"x"})
        return None

    monkeypatch.setattr(tools, "run_kaggle", fake_run_kaggle)

    result = await tools.kaggle_download_competition("titanic")

    assert result["status"] == "downloaded"
    files = set(result["files"])
    assert "train.csv" in files
    assert "test.csv" in files
    assert "titanic.zip" not in files
    # Disk state matches.
    assert not (Path(result["download_path"]) / "titanic.zip").exists()


@pytest.mark.asyncio
async def test_download_dataset_extracts_stale_zip(
    kaggle_download_root, disable_dataclaw_register, monkeypatch
):
    """Simulate the SDK no-op-on-cached path: a zip is present after the SDK call."""

    async def fake_run_kaggle(method, *args, **kwargs):
        path = Path(kwargs["path"])
        _drop_zip_into(path, "iris.zip", {"iris.csv": b"sepal,petal\n1,2\n"})
        return None

    monkeypatch.setattr(tools, "run_kaggle", fake_run_kaggle)

    result = await tools.kaggle_download_dataset("user/iris")

    assert result["status"] == "downloaded"
    assert result["files"] == ["iris.csv"]
    assert (Path(result["download_path"]) / "iris.csv").is_file()


@pytest.mark.asyncio
async def test_already_downloaded_self_heals_zip(
    kaggle_download_root, disable_dataclaw_register, monkeypatch
):
    """A cached registry entry whose dir contains a zip should self-heal on access."""
    # Pre-populate registry as if a prior download succeeded.
    dest = kaggle_download_root / "competitions" / "titanic"
    dest.mkdir(parents=True)
    registry.track_competition("titanic", {"title": "Titanic"})
    registry.record_download(
        kind="competitions",
        key="titanic",
        download_path=str(dest),
        files=["titanic.zip"],
        dataclaw_dataset_id="dataset-titanic",
    )
    _drop_zip_into(dest, "titanic.zip", {"train.csv": b"hi", "test.csv": b"bye"})
    enabled = []

    # run_kaggle must not be called on the already-downloaded path.
    async def boom(*args, **kwargs):
        raise AssertionError("run_kaggle should not be invoked when already downloaded")

    async def capture_enable(dataset_id, session_id):
        enabled.append((dataset_id, session_id))

    monkeypatch.setattr(tools, "run_kaggle", boom)
    monkeypatch.setattr(tools, "_enable_dataset_for_session", capture_enable)

    result = await tools.kaggle_download_competition(
        "titanic",
        dataclaw_session_id="session-1",
    )

    assert result["status"] == "already_downloaded"
    assert set(result["files"]) == {"train.csv", "test.csv"}
    assert result["dataclaw_dataset_id"] == "dataset-titanic"
    assert enabled == [("dataset-titanic", "session-1")]
    assert not (dest / "titanic.zip").exists()
    # Registry was refreshed.
    persisted = registry.get_competition("titanic")
    assert set(persisted["files"]) == {"train.csv", "test.csv"}


@pytest.mark.asyncio
async def test_cached_dataset_is_enabled_for_calling_session(
    kaggle_download_root, monkeypatch
):
    dest = kaggle_download_root / "datasets" / "owner_data"
    dest.mkdir(parents=True)
    (dest / "data.csv").write_text("value\n1\n")
    registry.track_dataset("owner/data", {"title": "Owner data"})
    registry.record_download(
        kind="datasets",
        key="owner/data",
        download_path=str(dest),
        files=["data.csv"],
        dataclaw_dataset_id="dataset-owner-data",
    )
    enabled = []

    async def boom(*args, **kwargs):
        raise AssertionError("run_kaggle should not be invoked when already downloaded")

    async def capture_enable(dataset_id, session_id):
        enabled.append((dataset_id, session_id))

    monkeypatch.setattr(tools, "run_kaggle", boom)
    monkeypatch.setattr(tools, "_enable_dataset_for_session", capture_enable)

    result = await tools.kaggle_download_dataset(
        "owner/data",
        dataclaw_session_id="session-2",
    )

    assert result["status"] == "already_downloaded"
    assert result["dataclaw_dataset_id"] == "dataset-owner-data"
    assert enabled == [("dataset-owner-data", "session-2")]


# ── Stale-cache recovery tests ─────────────────────────────────────────────


def test_is_valid_cached_download_missing_dir(tmp_path):
    """Path recorded in registry but no longer on disk → invalid cache."""
    entry = {
        "downloaded": True,
        "download_path": str(tmp_path / "gone"),
        "files": ["train.csv"],
    }
    assert tools._is_valid_cached_download(entry) is False


def test_is_valid_cached_download_empty_dir(tmp_path):
    """Path exists but empty (e.g., user deleted contents) → invalid cache."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    entry = {
        "downloaded": True,
        "download_path": str(empty_dir),
        "files": ["train.csv"],
    }
    assert tools._is_valid_cached_download(entry) is False


def test_is_valid_cached_download_with_files(tmp_path):
    populated = tmp_path / "good"
    populated.mkdir()
    (populated / "train.csv").write_text("a")
    entry = {
        "downloaded": True,
        "download_path": str(populated),
        "files": ["train.csv"],
    }
    assert tools._is_valid_cached_download(entry) is True


def test_is_valid_cached_download_none():
    assert tools._is_valid_cached_download(None) is False


def test_is_valid_cached_download_not_downloaded(tmp_path):
    entry = {"downloaded": False, "download_path": str(tmp_path)}
    assert tools._is_valid_cached_download(entry) is False


@pytest.mark.asyncio
async def test_download_competition_redownloads_when_path_deleted(
    kaggle_download_root, disable_dataclaw_register, monkeypatch
):
    """Stale registry pointing at a deleted directory triggers a fresh download."""
    dest = kaggle_download_root / "competitions" / "playground-series-s6e5"
    # NOTE: do not mkdir — simulating user deletion.
    registry.track_competition("playground-series-s6e5", {"title": "PS6E5"})
    registry.record_download(
        kind="competitions",
        key="playground-series-s6e5",
        download_path=str(dest),
        files=["playground-series-s6e5.zip"],
        dataclaw_dataset_id="3bdfed2b",
    )

    async def fake_run_kaggle(method, *args, **kwargs):
        path = Path(kwargs["path"])
        _drop_zip_into(
            path,
            "playground-series-s6e5.zip",
            {"train.csv": b"id,target\n1,0\n", "test.csv": b"id\n2\n"},
        )
        return None

    monkeypatch.setattr(tools, "run_kaggle", fake_run_kaggle)

    result = await tools.kaggle_download_competition("playground-series-s6e5")

    assert result["status"] == "downloaded"
    files = set(result["files"])
    assert files == {"train.csv", "test.csv"}
    # New download_path exists and is populated; zip removed.
    assert (Path(result["download_path"]) / "train.csv").is_file()
    assert not (Path(result["download_path"]) / "playground-series-s6e5.zip").exists()


@pytest.mark.asyncio
async def test_download_dataset_redownloads_when_path_deleted(
    kaggle_download_root, disable_dataclaw_register, monkeypatch
):
    dest = kaggle_download_root / "datasets" / "user_iris"
    registry.track_dataset("user/iris", {"title": "iris"})
    registry.record_download(
        kind="datasets",
        key="user/iris",
        download_path=str(dest),
        files=["iris.zip"],
    )

    async def fake_run_kaggle(method, *args, **kwargs):
        path = Path(kwargs["path"])
        _drop_zip_into(path, "iris.zip", {"iris.csv": b"a,b\n1,2\n"})
        return None

    monkeypatch.setattr(tools, "run_kaggle", fake_run_kaggle)

    result = await tools.kaggle_download_dataset("user/iris")

    assert result["status"] == "downloaded"
    assert result["files"] == ["iris.csv"]


@pytest.mark.asyncio
async def test_forced_download_reuses_existing_dataclaw_dataset_id(
    kaggle_download_root,
    monkeypatch,
):
    dest = kaggle_download_root / "competitions" / "titanic"
    dest.mkdir(parents=True)
    (dest / "old.csv").write_text("value\n1\n")
    registry.track_competition("titanic", {"title": "Titanic"})
    registry.record_download(
        kind="competitions",
        key="titanic",
        download_path=str(dest),
        files=["old.csv"],
        dataclaw_dataset_id="stable-id",
    )
    observed_existing_ids = []

    async def fake_run_kaggle(method, *args, **kwargs):
        Path(kwargs["path"]).mkdir(parents=True, exist_ok=True)
        (Path(kwargs["path"]) / "new.csv").write_text("value\n2\n")

    def fake_register(**kwargs):
        observed_existing_ids.append(kwargs["existing_dataset_id"])
        return kwargs["existing_dataset_id"]

    monkeypatch.setattr(tools, "run_kaggle", fake_run_kaggle)
    monkeypatch.setattr(tools, "_register_as_dataclaw_dataset", fake_register)

    result = await tools.kaggle_download_competition("titanic", force=True)

    assert result["dataclaw_dataset_id"] == "stable-id"
    assert result["dataset_registration"] == "registered"
    assert observed_existing_ids == ["stable-id"]


@pytest.mark.asyncio
async def test_registration_failure_is_returned_and_logged(
    kaggle_download_root,
    monkeypatch,
    caplog,
):
    async def fake_run_kaggle(method, *args, **kwargs):
        Path(kwargs["path"]).mkdir(parents=True, exist_ok=True)
        (Path(kwargs["path"]) / "data.csv").write_text("value\n1\n")

    def fail_registration(**kwargs):
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(tools, "run_kaggle", fake_run_kaggle)
    monkeypatch.setattr(tools, "_register_as_dataclaw_dataset", fail_registration)

    with caplog.at_level("ERROR"):
        result = await tools.kaggle_download_dataset("owner/data")

    assert result["status"] == "downloaded"
    assert result["dataset_registration"] == "failed"
    assert result["dataset_registration_error"] == "registry unavailable"
    assert any("Failed to register Kaggle download" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_session_attachment_failure_is_returned_and_logged(
    kaggle_download_root,
    monkeypatch,
    caplog,
):
    dest = kaggle_download_root / "datasets" / "owner_data"
    dest.mkdir(parents=True)
    (dest / "data.csv").write_text("value\n1\n")
    registry.track_dataset("owner/data", {"title": "Owner data"})
    registry.record_download(
        kind="datasets",
        key="owner/data",
        download_path=str(dest),
        files=["data.csv"],
        dataclaw_dataset_id="dataset-id",
    )

    async def fail_attachment(dataset_id, session_id):
        raise RuntimeError("session storage unavailable")

    monkeypatch.setattr(tools, "_enable_dataset_for_session", fail_attachment)

    with caplog.at_level("ERROR"):
        result = await tools.kaggle_download_dataset(
            "owner/data",
            dataclaw_session_id="session-id",
        )

    assert result["status"] == "already_downloaded"
    assert result["session_attachment"] == "failed"
    assert result["session_attachment_error"] == "session storage unavailable"
    assert any("Failed to enable dataset" in record.message for record in caplog.records)
