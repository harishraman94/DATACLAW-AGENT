"""dataclaw-context-research - cited external context for open-world problems."""

from __future__ import annotations

from dataclaw.plugins.base import (
    PluginConfigField,
    PluginContext,
    PluginUIManifest,
)
from dataclaw.providers.tool.implementations.python_tool import PythonTool

from dataclaw_context_research.router import router as context_router
from dataclaw_context_research.tools import (
    context_research_generate_queries,
    context_research_list_findings,
    context_research_save_to_okf,
    context_research_search_reddit,
    context_research_summarize_findings,
    set_plugin_cfg,
)


class ContextResearchPlugin:
    name = "dataclaw-context-research"
    depends_on = ["dataclaw-data", "dataclaw-okf"]

    def register(self, ctx: PluginContext) -> None:
        set_plugin_cfg(ctx.config.plugins.get("context-research", {}))
        ctx.include_api_router(context_router, prefix="/context-research", tags=["context-research"])

        tools = [
            (
                "context_research_generate_queries",
                "Generate open-world research queries from a dataset schema and/or problem statement",
                context_research_generate_queries,
                {
                    "type": "object",
                    "properties": {
                        "dataset_id": {"type": "string", "description": "Optional Dataclaw dataset ID", "default": ""},
                        "problem_statement": {"type": "string", "description": "Optional problem statement or analysis goal", "default": ""},
                        "limit": {"type": "integer", "description": "Maximum queries to return", "default": 8},
                    },
                },
            ),
            (
                "context_research_search_reddit",
                "Search Reddit for weak/community context about an open-world data problem",
                context_research_search_reddit,
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "dataset_id": {"type": "string", "description": "Optional dataset ID to attach findings to", "default": ""},
                        "problem_statement": {"type": "string", "description": "Optional problem statement", "default": ""},
                        "limit": {"type": "integer", "description": "Maximum results to fetch", "default": 10},
                        "subreddit": {"type": "string", "description": "Optional subreddit name", "default": ""},
                    },
                    "required": ["query"],
                },
            ),
            (
                "context_research_list_findings",
                "List saved external context findings with evidence labels and citations",
                context_research_list_findings,
                {
                    "type": "object",
                    "properties": {
                        "dataset_id": {"type": "string", "description": "Optional dataset filter", "default": ""},
                        "limit": {"type": "integer", "description": "Maximum findings to return", "default": 20},
                    },
                },
            ),
            (
                "context_research_summarize_findings",
                "Summarize saved external context findings by theme and evidence level",
                context_research_summarize_findings,
                {
                    "type": "object",
                    "properties": {
                        "dataset_id": {"type": "string", "description": "Optional dataset filter", "default": ""},
                        "finding_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional finding IDs"},
                    },
                },
            ),
            (
                "context_research_save_to_okf",
                "Save curated external context findings into an OKF bundle as notes/external_context.md",
                context_research_save_to_okf,
                {
                    "type": "object",
                    "properties": {
                        "bundle_id": {"type": "string", "description": "OKF bundle ID"},
                        "dataset_id": {"type": "string", "description": "Optional dataset filter", "default": ""},
                        "finding_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional finding IDs"},
                    },
                    "required": ["bundle_id"],
                },
            ),
        ]

        for name, description, fn, parameters in tools:
            ctx.tool_registry.register_tool(PythonTool(
                name=name,
                description=description,
                fn=fn,
                parameters=parameters,
            ))

    def ui_manifest(self) -> PluginUIManifest:
        return PluginUIManifest(
            id="context-research",
            label="Context Research",
            icon="search",
            pages=[],
            config_title="Context Research",
            config_fields=[
                PluginConfigField(
                    name="reddit_user_agent",
                    field_type="string",
                    label="Reddit User Agent",
                    description="User agent for public Reddit JSON requests",
                    default="DataclawContextResearch/0.1",
                ),
                PluginConfigField(
                    name="request_timeout",
                    field_type="int",
                    label="Request Timeout",
                    description="External request timeout in seconds",
                    default=12,
                ),
                PluginConfigField(
                    name="max_results",
                    field_type="int",
                    label="Max Results",
                    description="Maximum external results per search",
                    default=15,
                ),
            ],
        )
