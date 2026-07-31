"""Dataclaw Hermes runtime plugin."""

from __future__ import annotations

import logging

from dataclaw.plugins.base import (
    PluginConfigField,
    PluginContext,
    PluginUIManifest,
)

from dataclaw_hermes.bridge_router import router

logger = logging.getLogger(__name__)


class HermesPlugin:
    name = "dataclaw-hermes"
    depends_on: list[str] = []

    def register(self, ctx: PluginContext) -> None:
        ctx.include_api_router(router, prefix="/hermes", tags=["hermes"])

        async def _factory(factory_ctx):
            from dataclaw.providers.agent.factory import (
                RuntimeBundle,
                RuntimeDiagnostics,
                RuntimeIdentity,
            )
            from dataclaw_hermes.agent_provider import HermesAgentProvider
            from dataclaw_hermes.client import HermesClient
            from dataclaw_hermes.config import HermesConfig
            from dataclaw_hermes.health import verify_compatibility

            config = HermesConfig.resolve()
            config.validate()
            client = HermesClient(config)
            try:
                compatibility = await verify_compatibility(client)
                if config.model:
                    models = await client.models()
                    ids = {
                        str(item.get("id"))
                        for item in models.get("data") or []
                        if isinstance(item, dict)
                    }
                    if config.model not in ids:
                        raise RuntimeError(
                            f"Hermes model {config.model!r} is unavailable"
                        )

                base = factory_ctx.base_bundle
                runtime_store = ctx.app.state.runtime_run_store
                agent = HermesAgentProvider(client, config, runtime_store)
                return RuntimeBundle(
                    agent=agent,
                    utility_llm=base.utility_llm,
                    compaction=base.compaction,
                    tool_availability=base.tool_availability,
                    sub_agent_registry=base.sub_agent_registry,
                    sub_agent_hooks=base.sub_agent_hooks,
                    memory=base.memory,
                    system_prompt=base.system_prompt,
                    skill=base.skill,
                    hooks=factory_ctx.hooks.clone(),
                    runtime_control=client,
                    identity=RuntimeIdentity(
                        runtime="hermes",
                        version=compatibility["hermes_version"],
                        model=config.model,
                        provider=config.provider,
                    ),
                    diagnostics=RuntimeDiagnostics(
                        details={
                            "url": config.url,
                            "profile": config.profile,
                            "compat_version": compatibility[
                                "compat_version"
                            ],
                        }
                    ),
                )
            except Exception:
                await client.aclose()
                raise

        ctx.providers.register_runtime_factory("hermes", _factory)
        logger.info("Hermes plugin: runtime factory and routes registered")

    def ui_manifest(self) -> PluginUIManifest:
        fields = [
            PluginConfigField(
                "url",
                "string",
                "Hermes API URL",
                default="http://127.0.0.1:8642",
            ),
            PluginConfigField(
                "api_key",
                "string",
                "Hermes API key",
                description=(
                    "Required bearer key. The profile installer writes the "
                    "same value as API_SERVER_KEY; Hermes 0.19 requires it "
                    "even on loopback."
                ),
                default="",
            ),
            PluginConfigField(
                "dataclaw_api_url",
                "string",
                "Dataclaw callback URL",
                default="http://127.0.0.1:8000",
            ),
            PluginConfigField(
                "profile", "string", "Hermes profile", default="dataclaw"
            ),
            PluginConfigField(
                "model", "string", "Hermes model override", default=""
            ),
            PluginConfigField(
                "cli_path",
                "string",
                "Hermes CLI",
                description=(
                    "Hermes executable path. The standard uv-tool location "
                    "~/.local/bin/hermes is detected automatically."
                ),
                default="hermes",
            ),
            PluginConfigField(
                "request_timeout_seconds",
                "int",
                "Request timeout (seconds)",
                default=60,
            ),
            PluginConfigField(
                "reconnect_timeout_seconds",
                "int",
                "Reconciliation timeout (seconds)",
                default=30,
            ),
            PluginConfigField(
                "tool_callback_timeout_seconds",
                "int",
                "Tool callback timeout (seconds)",
                default=330,
            ),
        ]
        return PluginUIManifest(
            id="hermes",
            label="Hermes Agent",
            config_title="Hermes Runtime",
            config_fields=fields,
        )


__all__ = ["HermesPlugin"]
