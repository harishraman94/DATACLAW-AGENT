"""Async wrapper around the synchronous kaggle Python package."""

from __future__ import annotations

import asyncio
import os
import threading
from contextlib import contextmanager
from typing import Any

_api: Any = None
_api_signature: tuple[str, str, str] | None = None
_api_lock = threading.RLock()
_kaggle_api_cls: Any = None
_AUTH_ENV_VARS = ("KAGGLE_USERNAME", "KAGGLE_KEY", "KAGGLE_API_TOKEN")
_IMPORT_USERNAME = "__dataclaw_import__"
_IMPORT_KEY = "__dataclaw_import__"


def _normalise_credentials(
    username: str = "",
    key: str = "",
    api_token: str = "",
) -> tuple[str, str, str]:
    """Normalise legacy and current Kaggle credential formats.

    Older Dataclaw versions exposed only ``kaggle_key``. Kaggle's current
    "Generate New Token" flow returns a ``KGAT_...`` API token, which must be
    supplied as ``KAGGLE_API_TOKEN`` rather than as the legacy basic-auth key.
    Keep existing configurations working by detecting that token format.
    """
    username = username or ""
    key = key or ""
    api_token = api_token or ""
    if not api_token and key.startswith("KGAT_"):
        api_token = key
        key = ""
    return username, key, api_token


@contextmanager
def _safe_import_environment():
    """Import Kaggle without triggering its process-exiting auth prompt.

    ``kaggle.__init__`` authenticates a package-global client while importing.
    Harmless legacy placeholders keep that import side effect local and
    non-networked. Plugin credentials are never placed in ``os.environ``.
    Configured plugins eagerly perform this import before the config update
    completes. Unconfigured plugins keep it lazy, and the first tool call runs
    the guarded import in a worker thread.
    """
    previous = {name: os.environ.get(name) for name in _AUTH_ENV_VARS}
    try:
        os.environ["KAGGLE_USERNAME"] = _IMPORT_USERNAME
        os.environ["KAGGLE_KEY"] = _IMPORT_KEY
        os.environ.pop("KAGGLE_API_TOKEN", None)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _import_kaggle_api_class() -> Any:
    """Import hook kept separate for deterministic regression tests."""
    from kaggle.api.kaggle_api_extended import KaggleApi

    return KaggleApi


def prepare_client() -> None:
    """Eagerly load the Kaggle SDK for a configured plugin."""
    _load_kaggle_api_class()


def _load_kaggle_api_class() -> Any:
    """Load ``KaggleApi`` while containing its import-time auth behavior."""
    global _kaggle_api_cls
    with _api_lock:
        if _kaggle_api_cls is not None:
            return _kaggle_api_cls
        try:
            with _safe_import_environment():
                kaggle_api_cls = _import_kaggle_api_class()
        except SystemExit as exc:
            raise RuntimeError("Failed to initialize the Kaggle SDK") from exc
        _kaggle_api_cls = kaggle_api_cls
        return kaggle_api_cls


def _create_authenticated_api(
    username: str,
    key: str,
    api_token: str,
) -> Any:
    """Construct a Kaggle client with explicit, non-global credentials."""
    kaggle_api_cls = _load_kaggle_api_class()
    api = kaggle_api_cls()

    if api_token:
        config_values = {
            api.CONFIG_NAME_TOKEN: api_token,
            api.CONFIG_NAME_AUTH_METHOD: "ACCESS_TOKEN",
        }
        if username:
            config_values[api.CONFIG_NAME_USER] = username
        api.config_values = config_values
        return api

    if username or key:
        if not username or not key:
            raise RuntimeError(
                "Legacy Kaggle authentication requires both username and key"
            )
        api.config_values = {
            api.CONFIG_NAME_USER: username,
            api.CONFIG_NAME_KEY: key,
            api.CONFIG_NAME_AUTH_METHOD: "LEGACY_API_KEY",
        }
        return api

    _authenticate_api(api)
    return api


def _authenticate_api(api: Any) -> None:
    """Convert the Kaggle SDK's process-exit auth failure into a tool error."""
    try:
        api.authenticate()
    except SystemExit as exc:
        raise RuntimeError(
            "Kaggle authentication is not configured or the credential is invalid"
        ) from exc


def _get_api(
    username: str = "",
    key: str = "",
    api_token: str = "",
) -> Any:
    """Return a cached, authenticated KaggleApi instance.

    Import is deferred so the module loads even without credentials.
    Explicit plugin credentials take priority over host environment variables
    and Kaggle credential files, but are scoped to client construction.
    """
    global _api, _api_signature
    username, key, api_token = _normalise_credentials(username, key, api_token)
    signature = (username, key, api_token)
    with _api_lock:
        if _api is not None and _api_signature == signature:
            return _api
        api = _create_authenticated_api(username, key, api_token)
        _api = api
        _api_signature = signature
        return api


def reset_api() -> None:
    """Clear the cached client so the next call re-authenticates."""
    global _api, _api_signature
    with _api_lock:
        _api = None
        _api_signature = None


async def run_kaggle(
    method: str,
    *args: Any,
    username: str = "",
    key: str = "",
    api_token: str = "",
    **kwargs: Any,
) -> Any:
    """Authenticate and run a KaggleApi method without blocking the event loop."""
    return await asyncio.to_thread(
        _run_kaggle_sync,
        method,
        args,
        kwargs,
        username,
        key,
        api_token,
    )


def _run_kaggle_sync(
    method: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    username: str,
    key: str,
    api_token: str,
) -> Any:
    """Synchronous worker used by :func:`run_kaggle`."""
    api = _get_api(username, key, api_token)
    fn = getattr(api, method)
    return fn(*args, **kwargs)


def get_config(plugin_cfg: dict[str, Any]) -> tuple[str, str]:
    """Extract username and key from plugin config dict."""
    return (
        plugin_cfg.get("kaggle_username", "") or "",
        plugin_cfg.get("kaggle_key", "") or "",
    )


def get_auth_config(plugin_cfg: dict[str, Any]) -> dict[str, str]:
    """Return normalised credentials ready to pass to :func:`run_kaggle`."""
    username, key = get_config(plugin_cfg)
    api_token = plugin_cfg.get("kaggle_api_token", "") or ""
    username, key, api_token = _normalise_credentials(username, key, api_token)
    return {
        "username": username,
        "key": key,
        "api_token": api_token,
    }
