# Dataclaw Hermes runtime

Connects Dataclaw to a trusted local Hermes Agent API server. Dataclaw remains
the conversation, tool-policy, approval, and Runs surface; Hermes owns the
selected agent loop.

The supported compatibility target is `hermes-agent==0.19.0` on Python
3.11–3.13. Dataclaw itself requires Python 3.12 or newer, so Python 3.12 is the
shared compatible version. Install Hermes in an isolated tool environment with
its API-server dependency group:

```bash
uv tool install --python 3.12 'hermes-agent[messaging]==0.19.0'
```

Then use Dataclaw's Hermes installer to create the restricted `dataclaw`
profile and install the bundled extension. The installer requires
`plugins.hermes.api_key` because Hermes 0.19.0 requires bearer authentication
even when its API server binds only to loopback. Configure the primary model in
that profile with `hermes -p dataclaw model`, then select
`agent.runtime: hermes`.

Hermes 0.19.0's OpenAI-compatible chat endpoint runs a complete server-side
agent rather than exposing the raw tool-call continuation contract Dataclaw
needs for compaction and delegated sub-agents. Configure the shared DataClaw
utility provider with `llm.backend` and its model under `llm.<provider>.model`;
configure the primary provider/model separately in the Hermes `dataclaw`
profile.

Run a non-gating native batch evaluation from the Hermes checkout with:

```bash
dataclaw-hermes-eval \
  --hermes-root /path/to/hermes-agent \
  --dataset eval.jsonl \
  --run-name dataclaw-smoke \
  --model your-model-route
```

The command writes a JSON summary to stdout. Add `--summary result.json` to
persist the summary alongside your normal evaluation artifacts. The pinned
native runner assigns `task_<index>` IDs and does not create Dataclaw runs, so
this is a Hermes model/tool baseline only; the summary explicitly marks
`dataclawGovernanceCoverage: false`. Use the adapter integration tests for the
governed Dataclaw tool, approval, and Runs path.

This bridge does not add authentication to Dataclaw. Anyone who can reach the
Dataclaw API can use enabled tools, including host-level shell/notebook tools.
Run both APIs on loopback or a trusted private network.
