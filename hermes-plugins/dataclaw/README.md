# Dataclaw bridge for Hermes Agent

This Hermes plugin exposes only two model-visible tools:

- `dataclaw_tool` dispatches one Dataclaw-governed tool.
- `dataclaw_tool_search` searches the enabled Dataclaw catalog.

The `dataclaw` Hermes profile must whitelist only the `dataclaw` toolset for
the API-server platform. Dataclaw rechecks session/project tool availability,
runs its complete hook and guardrail chain, and owns approval and persistence.

The callback API is intentionally unauthenticated, matching the rest of the
Dataclaw API. Keep both services on loopback or a trusted private network.
