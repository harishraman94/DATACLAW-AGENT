"""Dataclaw Kaggle plugin — competitions, datasets, and submissions."""

from __future__ import annotations

from typing import Any

from dataclaw.plugins.base import (
    PluginConfigField,
    PluginContext,
    PluginPage,
    PluginUIManifest,
)
from dataclaw.providers.tool.implementations.python_tool import PythonTool

from dataclaw_kaggle.tools import (
    kaggle_list_competitions,
    kaggle_competition_details,
    kaggle_leaderboard,
    kaggle_download_competition,
    kaggle_search_datasets,
    kaggle_download_dataset,
    kaggle_submit,
    kaggle_submissions,
    set_plugin_cfg,
)
from dataclaw_kaggle.router import router as kaggle_router
from dataclaw_kaggle.router import set_plugin_cfg as set_router_cfg
from dataclaw_kaggle.client import get_auth_config, prepare_client, reset_api

_SESSION_AWARE_DOWNLOAD_TOOLS = frozenset({
    "kaggle_download_competition",
    "kaggle_download_dataset",
})


async def inject_kaggle_session_context(state: dict[str, Any]) -> dict[str, Any]:
    """Attach trusted session context to Kaggle download tool calls.

    Download tools use this hidden value to add newly registered datasets to
    the calling session's governed dataset allowlist. Always replace any
    model-supplied context value with the session from pipeline state.
    """
    session_id = str(state.get("session_id") or "")
    if not session_id:
        return state

    changed = False
    pending_calls = []
    for tool_call in state.get("pending_tool_calls", []):
        if tool_call.get("tool_name") not in _SESSION_AWARE_DOWNLOAD_TOOLS:
            pending_calls.append(tool_call)
            continue

        tool_input = dict(tool_call.get("tool_input") or {})
        tool_input.pop("session_id", None)
        tool_input["dataclaw_session_id"] = session_id
        pending_calls.append({**tool_call, "tool_input": tool_input})
        changed = True

    if not changed:
        return state
    return {**state, "pending_tool_calls": pending_calls}


class KagglePlugin:
    name = "dataclaw-kaggle"
    depends_on: list[str] = ["dataclaw-data"]

    @staticmethod
    def _apply_config(config: Any) -> None:
        """Refresh module-level plugin config and cached authentication."""
        plugin_cfg = config.plugins.get("kaggle", {})
        set_plugin_cfg(plugin_cfg)
        set_router_cfg(plugin_cfg)
        reset_api()

        # Kaggle authenticates a package-global client while importing. If
        # Dataclaw already has credentials, contain that import before the
        # config update completes. Keep the SDK lazy for unconfigured installs;
        # importing it adds substantial startup cost and the first tool call
        # already performs the same guarded import in a worker thread.
        auth = get_auth_config(plugin_cfg)
        if auth["api_token"] or (auth["username"] and auth["key"]):
            prepare_client()

    def register(self, ctx: PluginContext) -> None:
        # Pass plugin config to tools and router
        self._apply_config(ctx.config)

        # Downloads auto-register with dataclaw-data. Supply trusted request
        # context so the resulting dataset is immediately available to the
        # session that initiated the download.
        ctx.hooks.register("preToolCallHook", inject_kaggle_session_context)

        # Register API router
        ctx.include_api_router(kaggle_router, prefix="/kaggle", tags=["kaggle"])

        # Register tools
        ctx.tool_registry.register_tool(PythonTool(
            name="kaggle_list_competitions",
            description="List or search Kaggle competitions. Returns competition name, URL, deadline, reward, and team count.",
            fn=kaggle_list_competitions,
            parameters={
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Search term to filter competitions"},
                    "category": {
                        "type": "string",
                        "description": "Competition category",
                        "enum": ["all", "featured", "research", "gettingStarted", "playground", "analytics"],
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Sort order",
                        "enum": ["latestDeadline", "recentlyCreated", "numberOfTeams", "prize"],
                        "default": "latestDeadline",
                    },
                    "page": {"type": "integer", "description": "Page number", "default": 1},
                },
            },
        ))

        ctx.tool_registry.register_tool(PythonTool(
            name="kaggle_competition_details",
            description="Get detailed information about a specific Kaggle competition including data files, evaluation metric, and deadlines.",
            fn=kaggle_competition_details,
            parameters={
                "type": "object",
                "properties": {
                    "competition": {"type": "string", "description": "Competition slug (e.g. 'titanic')"},
                },
                "required": ["competition"],
            },
        ))

        ctx.tool_registry.register_tool(PythonTool(
            name="kaggle_leaderboard",
            description="View the leaderboard for a Kaggle competition. Returns top entries with team name, score, and rank.",
            fn=kaggle_leaderboard,
            parameters={
                "type": "object",
                "properties": {
                    "competition": {"type": "string", "description": "Competition slug"},
                    "page": {"type": "integer", "description": "Page number", "default": 1},
                },
                "required": ["competition"],
            },
        ))

        ctx.tool_registry.register_tool(PythonTool(
            name="kaggle_download_competition",
            description="Download data files for a Kaggle competition. Files are saved locally and registered as a dataclaw dataset. You must accept competition rules on kaggle.com before downloading.",
            fn=kaggle_download_competition,
            parameters={
                "type": "object",
                "properties": {
                    "competition": {"type": "string", "description": "Competition slug"},
                    "file_name": {"type": "string", "description": "Download a specific file instead of all files"},
                    "force": {"type": "boolean", "description": "Re-download even if already present", "default": False},
                },
                "required": ["competition"],
            },
        ))

        ctx.tool_registry.register_tool(PythonTool(
            name="kaggle_search_datasets",
            description="Search Kaggle datasets by keyword. Returns dataset ref, title, size, download count, and last updated date.",
            fn=kaggle_search_datasets,
            parameters={
                "type": "object",
                "properties": {
                    "search": {"type": "string", "description": "Search keyword"},
                    "sort_by": {
                        "type": "string",
                        "description": "Sort order",
                        "enum": ["hottest", "votes", "updated", "active", "published"],
                        "default": "hottest",
                    },
                    "file_type": {
                        "type": "string",
                        "description": "Filter by file type",
                        "enum": ["all", "csv", "sqlite", "json", "bigQuery"],
                    },
                    "page": {"type": "integer", "description": "Page number", "default": 1},
                },
                "required": ["search"],
            },
        ))

        ctx.tool_registry.register_tool(PythonTool(
            name="kaggle_download_dataset",
            description="Download a Kaggle dataset by its ref (owner/dataset-name). Files are saved locally and registered as a dataclaw dataset.",
            fn=kaggle_download_dataset,
            parameters={
                "type": "object",
                "properties": {
                    "dataset": {"type": "string", "description": "Dataset ref in owner/dataset-name format"},
                    "force": {"type": "boolean", "description": "Re-download even if already present", "default": False},
                },
                "required": ["dataset"],
            },
        ))

        ctx.tool_registry.register_tool(PythonTool(
            name="kaggle_submit",
            description="Submit a prediction file to a Kaggle competition. The file must exist locally.",
            fn=kaggle_submit,
            parameters={
                "type": "object",
                "properties": {
                    "competition": {"type": "string", "description": "Competition slug"},
                    "file_path": {"type": "string", "description": "Path to the submission file"},
                    "message": {"type": "string", "description": "Submission description message"},
                },
                "required": ["competition", "file_path", "message"],
            },
        ))

        ctx.tool_registry.register_tool(PythonTool(
            name="kaggle_submissions",
            description="List your submissions for a Kaggle competition with public/private scores, status, and ranking.",
            fn=kaggle_submissions,
            parameters={
                "type": "object",
                "properties": {
                    "competition": {"type": "string", "description": "Competition slug"},
                },
                "required": ["competition"],
            },
        ))

        # Default-disabled. Kaggle tools talk to a third-party API and
        # download large competition archives — opt-in is the safer
        # default. The user can toggle them on from the Tools page; the
        # seeded_plugins flag makes this a one-shot, so re-enables stick.
        ctx.tool_registry.seed_plugin_defaults(
            self.name,
            default_disabled=[
                "kaggle_list_competitions",
                "kaggle_competition_details",
                "kaggle_leaderboard",
                "kaggle_download_competition",
                "kaggle_search_datasets",
                "kaggle_download_dataset",
                "kaggle_submit",
                "kaggle_submissions",
            ],
        )

    def on_config_update(self, config: Any) -> None:
        """Apply Config-page changes without requiring a server restart."""
        self._apply_config(config)

    def ui_manifest(self) -> PluginUIManifest:
        return PluginUIManifest(
            id="kaggle",
            label="Kaggle",
            icon="trophy",
            pages=[PluginPage(path="/kaggle", label="Kaggle")],
            config_title="Kaggle Integration",
            config_fields=[
                PluginConfigField(
                    name="kaggle_api_token",
                    field_type="secret",
                    label="Kaggle API Token",
                    description="Recommended: token from Kaggle's Generate New Token flow (or set KAGGLE_API_TOKEN)",
                    default="",
                ),
                PluginConfigField(
                    name="kaggle_username",
                    field_type="string",
                    label="Legacy Kaggle Username",
                    description="Username from legacy kaggle.json credentials (or set KAGGLE_USERNAME)",
                    default="",
                ),
                PluginConfigField(
                    name="kaggle_key",
                    field_type="secret",
                    label="Legacy Kaggle API Key",
                    description="Key from legacy kaggle.json credentials (or set KAGGLE_KEY). Existing KGAT tokens saved here remain supported.",
                    default="",
                ),
                PluginConfigField(
                    name="download_dir",
                    field_type="string",
                    label="Download Directory",
                    description="Directory for downloaded Kaggle files (default: plugin data dir)",
                    default="",
                ),
                PluginConfigField(
                    name="auto_register_datasets",
                    field_type="bool",
                    label="Auto-Register Downloads",
                    description="Automatically register downloaded Kaggle data as dataclaw datasets",
                    default=True,
                ),
            ],
        )
