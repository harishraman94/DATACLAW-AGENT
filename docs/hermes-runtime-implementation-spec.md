# Hermes Runtime Implementation Specification

**Release:** Dataclaw 3.5  
**Authority:** Normative implementation contract  
**Architecture:** [Hermes Runtime Plan](hermes-runtime-plan.md)

## 1. Outcome

Implement `agent.runtime: hermes` as a first-class Dataclaw agent runtime.

> **Configuration update:** `agent.runtime` now selects `dataclaw`, `hermes`,
> or `openclaw`. `llm.backend` independently selects the DataClaw utility
> provider (`anthropic`, `openai`, `gemini`, or `codex`) used in every runtime.
> Legacy combined `llm.backend` configurations are migrated automatically.

The implementation MUST:

- use Hermes as the agent loop when globally selected;
- preserve Dataclaw conversation history, tool configuration, guardrails,
  approvals, session persistence, and Runs projection;
- work without OpenClaw;
- support structured lifecycle, Dataclaw tool search, governed Dataclaw tools, a
  single configured Hermes model, and native batch evaluation;
- preserve current Direct and OpenClaw behavior;
- follow Dataclaw's existing local/private trust model.

This release does not add a general authentication, TLS, sandbox, or multi-user
security boundary.

### Execution rule for Codex

Implement one numbered phase at a time:

1. inspect the named files before changing them;
2. confirm the previous phase gate;
3. preserve unrelated working-tree changes;
4. add tests with each production change;
5. report phase-gate evidence before beginning the next phase.

Phase 0 is investigative. Do not implement a speculative adapter against
unverified Hermes events or hooks.

## 2. Scope

### 2.1 Required

- Pinned Hermes version and compatibility fixtures.
- Central provider selection via a two-pass startup sequence, returning an
  immutable runtime bundle.
- An immutable per-run runtime bundle — every reloadable provider and hook the loop
  reads (agent, utility LLM, compaction, tool availability, sub-agent registry and
  hooks, memory, system prompt, skill, hook registry) — captured at run start and
  reachable by callbacks through a process-local `runId → ActiveRunContext` lease.
- `run_id` and the resolved project scope carried in `AgentState`, validated at
  the Hermes boundary.
- A required real Dataclaw utility LLM for compaction and
  `delegate_to_subagent`.
- Structured external-runtime broker/Runs events.
- Durable Hermes run and tool-call correlation records, with in-process tool-call
  idempotency (lock/future + canonical-argument hashing).
- Installable Dataclaw Hermes adapter.
- Independent Hermes Dataclaw extension.
- Dataclaw tool-search and tool-call routes; enabled tools reach Hermes through the
  Phase-0-verified mechanism (§3.3 gate 10), fed by one shared enabled-tool
  resolver.
- Existing Dataclaw guardrail, approval, hook, event, and persistence behavior
  applied to Hermes tools.
- A single chat-router terminalization helper (success, failure, cancellation,
  duplicate terminal signal).
- A single configured Hermes model (profile main model, optionally overridden
  through `plugins.hermes`).
- A runtime-control protocol (`cancel`/`status`) — optional for a generic bundle,
  mandatory for Hermes — driven by the captured bundle.
- Configuration, setup, health, diagnostics, UI, packaging, and tests.
- Native Hermes batch evaluation as a non-blocking harness.

### 2.2 Excluded

Do not implement:

- Hermes-native structured delegation (parent/child admission, depth/fan-out) —
  3.5 reuses the existing `delegate_to_subagent` tool through the Hermes tool
  route;
- Dataclaw-owned scheduled jobs, occurrences, schedulers, or Hermes background
  dispatch;
- a policy-based model-route engine, multiple named routes, per-work-kind
  `allowed_work`, budgets, or a top-level `runtime_routes` config key;
- adapter-side terminal-message persistence, stable terminal IDs, or terminal
  digests — the chat router remains the sole terminal-message writer;
- durable approval recovery, cross-restart approval reattachment, or
  event-watermark replay — approval and streaming continuity are
  process-lifetime only;
- concurrent multi-tool tracking or an aggregate multi-call approval count — 3.5
  serializes Dataclaw tool callbacks per Hermes run;
- native Hermes Tool Search (deferrable-tool progressive disclosure); enabled
  tools reach Hermes through the Phase-0-verified mechanism (§3.3 gate 10);
- a shared tool executor for Direct, OpenClaw, and Hermes;
- migration of the OpenClaw tool proxy;
- bridge-only authentication, execution tokens, TLS, or sandboxing;
- per-session runtime stamps, adoption, or fork UX;
- persistent goals or goal APIs;
- Hermes-native memory or learning;
- Hermes-native file, terminal, browser, web, or cron tools;
- Hermes skill mutation;
- model-visible `execute_code`;
- OpenClaw tools, plugins, memory, gateway, or session APIs inside Hermes;
- session forks, context engines, Kanban, Honcho, Curator, multiple profiles, or
  inline image transport;
- a database migration or general workflow engine.

## 3. Phase 0 compatibility gate

No production Hermes release may ship until this section passes against an exact
pinned Hermes version. Source-contract fixtures may unblock adapter construction,
but they do not replace the live release gate.

### 3.1 Pin and record

Record:

- package name and exact version;
- source revision for any patch;
- Python and operating-system requirements;
- license and redistribution result;
- API-server startup command;
- required optional dependency groups;
- patch files and upstream issue links, if applicable.

Update the lockfile with the tested version.

### 3.2 Capture fixtures

Capture sanitized fixtures for:

- health;
- ordinary streaming;
- text delta;
- tool request and result;
- a tool request held pending and then completed;
- usage;
- completion;
- failure;
- cancellation;
- reconnect to running and completed work;
- a utility model call exercising the full contract (streamed text and tool
  calls), if Hermes exposes one;
- native batch output, partial failure, and cancellation.

Fixtures MUST come from the pinned implementation rather than documentation
examples.

### 3.3 Prove

Automated tests MUST prove:

1. Streaming provides stable text, progress, usage, completion, failure, and
   cancellation signals.
2. A stable Hermes `tool_call_id` reaches the Dataclaw tool handler.
3. A Dataclaw tool handler may remain pending while user approval is collected.
4. The correlated result resumes the correct Hermes tool call.
5. Stop and reconnect distinguish running, completed, failed, cancelled, and
   unknown.
6. The Dataclaw Hermes profile can exclude every native tool disabled by this
   specification.
7. Required Hermes packages and extension mechanisms are distributable.
8. Dataclaw-supplied correlation (`runId`, `sessionId`) is echoed back on the
   tool callback, not only the `tool_call_id`. The correlation design in §12.2
   depends on this round-trip.
9. The Hermes tool-callback client timeout can be configured above the Dataclaw
   approval window. Record the maximum tunable value; if it is below the
   window, §12.3 shortens the Dataclaw approval wait to fit.
10. The session's enabled Dataclaw tools reach Hermes through a concrete supported
    mechanism — per-run tool filtering, a generic Dataclaw dispatch tool, or a
    pinned patch — **and** disabled tools are absent from the model-visible schemas
    (prove absence, not just presence). Prompt-only allowlisting is insufficient.
    Record the exact mechanism: the Runs API accepts input/session/instructions/
    history, not a per-request tool manifest, and Hermes plugin tools register into
    a global registry. If neither per-run filtering nor a patch is available, the
    generic Dataclaw dispatch tool is the guaranteed fallback (the model sees only
    the dispatch/search tools; Dataclaw enforces enablement server-side) — the
    design changes to that exposure rather than stalling.
11. A usable Hermes model endpoint satisfies the **full `LLMProvider` contract**
    utility work needs — system+message input, tool-schema input, streamed text,
    stable tool calls, correlated tool-result continuation, and multi-turn
    completion — not merely text completion. Compaction needs text; sub-agent
    delegation needs tool calls and `build_tool_result_message`. If the endpoint
    cannot, record it so §10.1 uses a Dataclaw-configured fallback utility model.
12. Determine whether Hermes can redeliver stream events (at-least-once). The
    §9.1 event-dedup set is required only if it can; otherwise the live `cursor`
    suffices.

### 3.4 Missing upstream contract

Prefer a supported Hermes extension point. If none exists, a small pinned patch is
allowed only when:

- a fixture test demonstrates the missing behavior;
- the patch is isolated from Dataclaw product logic;
- the patched version is pinned;
- an upstream-removal path is documented.

Do not simulate lifecycle or approval guarantees through prompting. Stop the
dependent phase if the contract cannot be provided safely.

### 3.5 Recorded implementation target

The adapter targets `hermes-agent==0.19.0`, tag `v2026.7.20`, revision
`3ef6bbd201263d354fd83ec55b3c306ded2eb72a`, under the MIT license. Upstream
requires Python `>=3.11,<3.14`; Hermes therefore runs in its own compatible
environment rather than Dataclaw's current Python 3.14 environment. No upstream
patch is used.

Install the pinned package with its `messaging` extra:

```bash
uv tool install --python 3.12 'hermes-agent[messaging]==0.19.0'
```

The extra supplies `aiohttp==3.14.1`, which the Hermes API-server adapter
requires. The base `hermes-agent==0.19.0` installation alone can run the
gateway supervisor but cannot bind the API server.

Inspection of that pinned source established the implemented contracts:

- Runs use `input`, `session_id`, `instructions`, and an optional model route;
  no per-request provider override is supported.
- The extension receives the stable `tool_call_id` at `pre_tool_call`; a
  task-local handoff carries it to the generic dispatcher.
- API-server tool exposure is global, so the dedicated profile enables only the
  `dataclaw` toolset containing `dataclaw_tool` and
  `dataclaw_tool_search`. Dataclaw rechecks the session allowlist.
- Run event queues are process-local and have no replay. A dropped stream is
  failed/unknown rather than synthesized as complete from a later status read.
- `/v1/chat/completions` executes a full server-side agent and cannot satisfy
  Dataclaw's raw utility `LLMProvider` continuation contract. A configured
  Dataclaw utility backend/model is mandatory.

Sanitized source-contract fixtures live under
`plugins/dataclaw-hermes/tests/fixtures`. They deliberately record
`"liveCapture": false`; ordinary chat, tool, approval, cancellation, reconnect,
and batch fixtures must still be captured from a live Python-3.11–3.13 Hermes
0.19.0 installation before release.

## 4. Current baseline

Implementation begins from these repository facts:

- `AgentProvider.stream_turn(state)` is the agent-runtime boundary.
- `AgentState` (a `TypedDict`, `total=False`) carries `session_id`, `project_id`,
  `user_query`, `messages`, and pipeline fields. It does **not** carry `run_id` or
  any workspace id, and its optional fields are not guaranteed present — the
  adapter MUST validate correlation fields rather than assume them. `run_id`
  exists only on the run loop and the `current_emitter` contextvar.
- The codebase's unit of project scope is `projectId`. There is no first-class
  `workspaceId`; "workspace" is only a filesystem partition derived from the
  session id.
- Existing provider events cover text, tool start, pending tool calls, and
  completion (`BrokerEvent = TextDeltaEvent | ToolUseStartEvent | PendingToolCall
  | TurnCompleteEvent`). `_run_agent_loop` decodes exactly those four.
- The run loop reads `providers.llm`, `providers.compaction`,
  `providers.tool_availability`, and the sub-agent provider **fresh during a
  turn**, not only `providers.agent`; a mid-run reload can otherwise mix
  old-agent and new-LLM behavior. This is a latent Direct bug the bundle snapshot
  (§10.3) also closes.
- The chat router is the terminal-message writer for the built-in provider; it
  persists one assistant message per turn on success. On failure it emits
  `run_error` and finishes the run but does **not** persist a terminal error
  message.
- `RunTracker` is process-local with running, finished, and error states and a
  monotonic per-run `cursor`.
- Direct orchestrates tool hooks, approvals, execution, events, and persistence in
  the chat router.
- The only tool approval today is the guardrail `user_approval` gate, held in
  memory on the run (`guardrail_approvals` / `guardrail_decisions` on `RunState`)
  and released through `POST /agent/guardrail/{thread_id}/{approval_id}` with a
  300 s timeout→deny. It does not survive a restart.
- The OpenClaw tool proxy resolves and invokes Dataclaw tools but does **not**
  pause for approval — it hard-denies a removed call. It also does not set the
  `current_thread_id` / `current_emitter` contextvars, and it locates the run by
  session/status only, not by `run_id`.
- `delegate_to_subagent` depends on `current_thread_id` and `current_emitter` for
  progress emission and conversation persistence; the chat loop sets them.
- Provider construction happens in `init_providers()` before plugins are
  discovered and registered; `_bootstrap_plugin_defaults` runs after registration.
  `LangChainAgentProvider(llm)` and `DefaultSubAgentProvider(llm)` are both bound
  to the single `llm_from_config()` object.
- The built-in `llm_from_config()` returns `MockLLM` for non-model backends such
  as `openclaw`. A runtime that reuses compaction and `delegate_to_subagent`
  MUST supply a real LLM instead.
- Legacy `llm.backend` values combined external runtimes with model providers.
  Migration separates them into `agent.runtime` and the utility-only
  `llm.backend`.
- Configuration has no `${ENV}` interpolation; values resolve through named
  environment variables and are masked on display. The resolver is flat
  (`resolve(dot_path, env_var, default)`) and does not round-trip nested config.
- Sessions are JSON records with no runtime stamp; the store writes in place under
  per-session in-process locks, with no atomic rename and no compare-and-set.
  `append_message` deduplicates by `messageId`.
- The Dataclaw API has no authentication.

Do not assume a provider factory, durable runtime mapping store, or shared tool
executor already exists.

### 4.1 Dataclaw change inventory

Implement these changes outside the Hermes HTTP/SSE client:

1. Add a central provider factory, invoked by a **post-registration selection
   pass** (two-pass startup), that returns an immutable runtime bundle. Route every
   existing reload caller through it, including the Codex-login hot reload
   (`codex_auth.py`).
2. Register external provider factories during plugin registration without
   replacing the active provider.
3. Capture the immutable runtime bundle once at run start (agent, utility LLM,
   compaction, tool availability, sub-agent, hooks) and register it in a
   process-local `runId → ActiveRunContext` lease so callbacks resolve it; use it
   for the whole turn, cancellation, and status.
4. Add `run_id` and the resolved project scope to `AgentState`, and validate them
   at the Hermes boundary.
5. Provide a real configured Dataclaw utility LLM for compaction and
   `delegate_to_subagent` — never `MockLLM`.
6. Extend broker and Runs lifecycle events (§9) and introduce shared
   `is_live`/`is_terminal` status helpers, routing every existing `status ==
   "running"` comparison (SSE exit, second-turn admission, cancellation) through
   them.
7. Add a small durable store for Hermes run and tool-call correlations with
   in-process tool-call idempotency.
8. Add a Hermes-specific tool/search router and tool executor that sets and
   resets the request contextvars (`current_thread_id`, `current_emitter`,
   `current_runtime_bundle`) through a context manager, and reject a turn at
   `/agent` admission when the active bundle is unavailable, before any session
   mutation.
9. Add a single chat-router terminalization helper that all runtimes use.
10. Add a single configured Hermes model and usage projection.
11. Add Hermes configuration, setup, health, diagnostics, UI, packaging, and
    evaluation.

The chat router remains the sole terminal-message writer; there is no
adapter-side terminal store or restart replay. Do not change Direct tool
orchestration or the OpenClaw tool proxy. OpenClaw receives the same DataClaw
utility bundle as Hermes.

## 5. Invariants

1. `agent.runtime` is the only global runtime selector. `llm.backend` selects
   the DataClaw utility provider independently.
2. Plugin registration does not replace the active provider; it registers a
   runtime factory.
3. Startup and reload converge on the same post-registration selection pass and
   swap the whole runtime bundle atomically after health checks.
4. An in-flight run retains its captured runtime bundle.
5. A later turn may use a newly selected runtime with the same Dataclaw history.
6. Dataclaw IDs and Hermes IDs remain separate opaque fields.
7. Ordinary Hermes turns do not rely on Hermes session memory.
8. Hermes tools resolve through Dataclaw's enabled-tool service.
9. The leased bundle's complete pre- and post-tool hook chains run for Hermes calls
   (including the capability filters), with `current_thread_id`, `current_emitter`,
   and `current_runtime_bundle` set and always reset.
10. Approval is required whenever existing guardrail behavior requires it, using
    the existing in-memory approval maps and endpoint.
11. A repeated or concurrent Hermes tool call does not execute twice, distinct
    tool calls are serialized per run, and no tool call executes after its run
    reaches a terminal state.
12. Transient network loss fails the current turn (the user retries); the run is
    not left indefinitely pending and no partial terminal message is written.
13. Exactly one terminal assistant message is persisted **by the chat router** on
    success; failures are event-only (matching Direct); the Hermes adapter
    persists no terminal state.
14. In Hermes mode, compaction and sub-agent delegation use a real configured
    LLM, never `MockLLM`; delegated child turns run on the utility LLM through
    `DefaultSubAgentProvider`, not on Hermes.
15. The Hermes bridge routes run in the same process as the chat API (guardrail
    approval is an in-memory `asyncio.Event`) and resolve the run's captured bundle
    from the process-local `runId → ActiveRunContext` lease.
16. Cancellation, status, and delegated sub-agent resolution use the captured
    runtime bundle (via `current_runtime_bundle`), not the current global
    selection.
17. Hermes-native memory, learning, cron, delegation, and unrestricted native
    tools remain disabled.
18. Correlation validation is a correctness check, not an authentication claim.

## 6. Source surfaces

The layout below is normative unless an implementation review records an
equivalent ownership boundary.

### 6.1 Shared Dataclaw core

Add:

```text
dataclaw/providers/agent/factory.py
dataclaw/storage/runtime_runs.py
```

Modify:

```text
dataclaw/providers/agent/provider.py
dataclaw/providers/llm/provider.py
dataclaw/state.py
dataclaw/api/context.py
dataclaw/api/routers/codex_auth.py
dataclaw/api/run_tracker.py
dataclaw/api/routers/chat.py
dataclaw/api/routers/config.py
dataclaw/api/deps.py
dataclaw/api/app.py
dataclaw/config/schema.py
dataclaw/plugins/registry.py
pyproject.toml
```

Core changes MUST remain runtime-neutral. Core MUST NOT import a runtime plugin
package directly. The factory returns an immutable runtime bundle; the terminal
helper lives in `chat.py`.

### 6.2 Dataclaw Hermes adapter

Add:

```text
plugins/dataclaw-hermes/
  pyproject.toml
  README.md
  dataclaw_hermes/
    __init__.py
    agent_provider.py
    bridge_router.py
    client.py
    config.py
    events.py
    health.py
    identity.py
    installer.py
    tool_executor.py
    eval.py
```

The package MUST follow the Dataclaw plugin entry-point convention. It MUST NOT
import OpenClaw. `bridge_router.py` MUST be mounted on the same FastAPI app as the
chat router (in-process; see invariant 15). Hermes 0.19.0 does not expose the raw
utility-model continuation contract, so utility work uses the required configured
Dataclaw fallback.

### 6.3 Hermes Dataclaw extension

Add a versioned extension in the format verified during Phase 0:

```text
hermes-plugins/dataclaw/
  README.md
  pyproject.toml
  dataclaw_hermes_bridge/
    __init__.py
    catalog.py
    tools.py
    correlation.py
```

This package talks only to the Dataclaw Hermes routes. It does not load OpenClaw
plugins or Dataclaw tool implementations.

### 6.4 OpenClaw

Modify only provider registration if required:

```text
plugins/dataclaw-openclaw/dataclaw_openclaw/__init__.py
```

Do not refactor:

```text
plugins/dataclaw-openclaw/dataclaw_openclaw/tool_proxy.py
```

### 6.5 UI

At minimum modify:

```text
ui/src/pages/ConfigPage.tsx
```

Add:

- Hermes runtime selection;
- Hermes configuration and health;
- configured-versus-active status;
- incompatible-runtime diagnostics;
- approval events in Runs.

Do not add runtime-stamp, adopt/fork, delegation, job, or goal UI.

### 6.6 Delegation reload-safety

Modify:

```text
dataclaw/api/context.py
plugins/dataclaw-projects/dataclaw_projects/__init__.py
plugins/dataclaw-projects/dataclaw_projects/tools.py
```

Add a `current_runtime_bundle` contextvar and have `delegate_to_subagent` read the
sub-agent registry and hooks from it rather than the global `providers` registry
(§10.3). This also fixes a latent Direct-mode reload hole.

## 7. Configuration

### 7.1 Selector

```yaml
agent:
  runtime: hermes
llm:
  backend: openai
  openai:
    model: gpt-4o-mini
```

Valid runtime values are `dataclaw | openclaw | hermes` (plus `mock` for
testing). Valid utility providers are `anthropic | openai | gemini | codex`.
With `agent.runtime: dataclaw`, the utility model also runs the primary agent.

### 7.2 Hermes

```yaml
plugins:
  hermes:
    url: http://127.0.0.1:8642
    api_key: "generated-shared-key"    # required by Hermes 0.19.0, including on loopback
    dataclaw_api_url: http://127.0.0.1:8000
    profile: dataclaw
    model: ""                          # optional; defaults to the profile's main model
    provider: ""                       # MUST remain empty for Hermes 0.19.0
    cli_path: hermes
    request_timeout_seconds: 60
    reconnect_timeout_seconds: 30
    tool_callback_timeout_seconds: 330 # MUST exceed the approval window (§12.3)
```

Rules:

- Configure Hermes through the Config page like OpenClaw. Values resolve through
  the existing `resolve(dot_path, env_var, default)` mechanism (named env var
  overrides the stored value); there is no `${ENV}` interpolation.
- `api_key` is **required**. Hermes 0.19.0 refuses to start the API server
  without `API_SERVER_KEY`, including for a loopback-only bind. The profile
  installer writes the same value to `platforms.api_server.extra.key`. This is
  outbound authentication to Hermes, not a new Dataclaw boundary.
- `tool_callback_timeout_seconds` governs how long Hermes waits on a Dataclaw tool
  callback. The waiting client lives in the Hermes extension, so the
  installer/profile generator MUST propagate this value into the Hermes extension
  configuration — storing it in Dataclaw alone enforces nothing. It MUST exceed
  the Dataclaw approval window plus a safety margin; startup validation rejects a
  value that does not. It is a distinct path from `request_timeout_seconds` (the
  outbound Dataclaw→Hermes request).
- Phase 0 gate 11 found that Hermes 0.19.0 `/v1/chat/completions` executes the
  server-side agent and does not expose raw tool-call/result continuation.
  Therefore the global `llm.backend` provider and its configured model are
  required for compaction and `delegate_to_subagent`. The result must never be
  `MockLLM`.
- `reconnect_timeout_seconds` bounds status/cancellation reconciliation queries
  against Hermes; it does not enable stream replay (which is not implemented).
- Credentials follow current Dataclaw storage behavior (plain text in the config
  file, masked on display).
- Do not log resolved credentials.
- Hermes configuration may exist while another backend is active.
- Selecting Hermes with invalid settings produces an unhealthy/incompatible
  runtime state; it does not fall back to Direct.
- The profile defaults to `dataclaw`.
- `dataclaw_api_url` defaults to loopback.
- A non-loopback URL displays the same local/private deployment warning as the
  main Dataclaw configuration.

### 7.3 Model selection

3.5 does not add a route engine or a top-level `runtime_routes` key (the flat
config resolver does not round-trip nested route definitions, and multi-route
policy is deferred to align with the planned Sprint-2 OpenRouter per-sub-agent
routing).

- Hermes uses the selected profile's main model by default.
- To override the model, set `plugins.hermes.model` to a configured Hermes model
  route. Hermes 0.19.0 `/v1/runs` ignores a `provider` field, so
  `plugins.hermes.provider` must remain empty and provider selection belongs in
  the Hermes profile/model route.
- Compaction and `delegate_to_subagent` use the required Dataclaw utility model
  (§7.2). Delegated child turns run through `DefaultSubAgentProvider`; they do not
  recurse into Hermes.
- Keep provider credentials outside prompts and events.
- A missing or invalid model fails before work begins.

## 8. Persistence

Use JSON storage consistent with the existing session store: per-record
in-process locking and best-effort writes. Do not introduce a database for
Hermes.

Lifecycle transitions carry a `revision` field for optimistic conflict detection
within the process. Atomic-rename and cross-process compare-and-set are **not**
required or implied and are not provided by the existing store; a future release
that adds cross-process scheduling must introduce that guarantee explicitly rather
than assume it here.

### 8.1 Runtime run record

The durable run record is created **before** contacting Hermes, keyed by the
Dataclaw `runId`. The opaque Hermes identifiers are upserted when they first
arrive on the stream. This ordering lets a tool callback correlate by `runId`
even if it arrives before the stream reveals the `runtimeRunId`.

```json
{
  "runId": "Dataclaw run id",
  "runtime": "hermes",
  "workKind": "chat",
  "sessionId": "Dataclaw session id",
  "projectId": "Dataclaw project id",
  "runtimeSessionId": "opaque nullable value",
  "runtimeRunId": "opaque nullable value",
  "runtimeTaskId": "opaque nullable value",
  "status": "queued | running | waiting_approval | stopping | completed | failed | cancelled | unknown",
  "revision": 0,
  "createdAt": "ISO-8601",
  "updatedAt": "ISO-8601"
}
```

`workspaceId` is not a separate concept: the run's project scope is the Dataclaw
`projectId`. There is no `route`, `terminalMessageId`, `terminalDigest`, or event
watermark on the record — the chat router owns terminal persistence (§11) and
there is no cross-restart replay (§11.4).

`unknown` marks a run whose outcome could not be confirmed within the process
lifetime. On restart, persisted non-terminal runs are marked failed and never
resumed.

Allowed run-status transitions (terminal states are immutable; a write that would
overwrite a terminal state is rejected):

```text
queued → running | failed | cancelled
running ↔ waiting_approval
running → stopping
running → completed | failed | cancelled | unknown
waiting_approval → stopping | failed | cancelled | unknown
stopping → completed | cancelled | failed | unknown
unknown → completed | failed | cancelled          # status reconciliation
```

Terminal precedence: once a run is `completed`, `failed`, or `cancelled`, later
signals do not change it, and a late `unknown` never overrides a terminal state.
`unknown` is itself non-executable — no new tool call is admitted under it and it
never returns to `running`; it reconciles only to `completed`/`failed`/`cancelled`
or is marked failed on restart. The `revision` field guards concurrent writes but
does not by itself forbid an invalid transition — enforce the table.

Status classification, used everywhere a status is compared:

- **live** — `queued`, `running`, `waiting_approval`, `stopping`;
- **terminal** — `completed`, `failed`, `cancelled`;
- `unknown` — neither live nor terminal (reconciles, or is failed on restart).

Introduce shared `is_live()` / `is_terminal()` helpers and route every status
comparison through them, because the current code treats only literal `running` as
active: SSE MUST stay open while a run is live (not only `running`); a second
`/agent` turn MUST recognize any live run and never replace one that is
`waiting_approval` or `stopping`; cancellation MUST be accepted while a run is live.
Audit every existing `status == "running"` site.

### 8.2 Tool-call record

Idempotency key:

```text
(runtimeRunId, toolCallId)
```

Concurrency is enforced in-process: a per-key lock/future ensures that identical
concurrent retries await or return the first execution's result, conflicting
arguments fail immediately, and an ambiguous execution becomes `unknown`. The JSON
record alone cannot prevent concurrent duplicate execution. `argumentsDigest` is a
sha256 over a canonical (key-sorted) JSON encoding of the arguments.

Record:

```json
{
  "runtimeRunId": "opaque Hermes run id",
  "toolCallId": "stable Hermes call id",
  "dataclawRunId": "Dataclaw run id",
  "sessionId": "Dataclaw session id",
  "projectId": "Dataclaw project id",
  "toolName": "canonical name",
  "argumentsDigest": "sha256",
  "state": "received | waiting_approval | approved | denied | executing | completed | failed | unknown",
  "approvalId": "nullable",
  "result": "nullable result envelope",
  "revision": 0
}
```

The result envelope is:

```json
{
  "state": "completed | denied | failed | executing | unknown",
  "isError": false,
  "content": "tool result payload or error message",
  "guardrailId": "nullable"
}
```

Retry semantics for an identical `(runtimeRunId, toolCallId)`:

- `completed` → return the stored result; do not re-execute;
- `denied` → return the stored denial; do not re-prompt or execute;
- `failed` → return the stored failure; do not re-execute — a genuine retry MUST
  use a new call id;
- `executing` → await the first invocation's result;
- `unknown` → return an explicit non-executing reconciliation error; never execute
  a second time.

`content` is arbitrary JSON (the tool's structured result), JSON-encoded into the
session tool-call message per existing behavior — not a pre-serialized string.
HTTP status on the call route: `completed`, `denied`, and `failed` return **200**
with the envelope (`isError` distinguishes them, so Hermes delivers the outcome to
the model as a tool result); `executing` awaits the first invocation and returns
its terminal envelope; `unknown` returns **409** with a non-executing reconciliation
error; a correlation or mapping mismatch returns **404/400** (not a tool outcome).

A changed tool name or argument digest under the same key fails. Tool-call terminal
states (`completed`, `denied`, `failed`, `unknown`) are immutable and
non-executable. Allowed forward paths:

```text
received → executing                              # no approval required
received → waiting_approval                       # approval required
received → denied                                 # immediate guardrail denial
received → failed | unknown
waiting_approval → approved | denied
waiting_approval → failed | unknown               # restart/drop while awaiting approval
approved → executing | failed | unknown
executing → completed | failed | unknown
```

## 9. Broker and Runs events

The adapter's internal lifecycle vocabulary is:

```text
RuntimeAccepted
RuntimeProgress
ToolDiscovered
ToolCallProposed
ApprovalRequired
ToolCallStarted
ToolCallCompleted
ToolCallFailed
UsageReported
RuntimeCompleted
RuntimeFailed
RuntimeCancelled
```

Every event includes:

- Dataclaw `run_id`;
- monotonic per-run sequence when Hermes supplies one;
- timestamp;
- runtime;
- relevant correlation identifiers;
- bounded user-visible payload.

### 9.1 Consumption

The current `BrokerEvent` union is `TextDeltaEvent | ToolUseStartEvent |
PendingToolCall | TurnCompleteEvent`, and `_run_agent_loop` decodes exactly those.
The lifecycle vocabulary above is **not** yielded as new `BrokerEvent` variants
the loop cannot decode. Instead:

- Assistant text → `TextDeltaEvent`.
- The turn ends with `TurnCompleteEvent(skip_persist=False)`; the chat router's
  terminalization helper persists the assistant message (§11.3).
- Tool lifecycle, progress, and usage events are emitted **directly to the
  RunTracker** from the Hermes adapter or tool route, as the existing emitter
  event strings the UI already renders — the same pattern the OpenClaw tool proxy
  uses.
- `ApprovalRequired` MUST be emitted as the existing `guardrail:approval_required`
  custom event so the current approval UI and its
  `/agent/guardrail/{thread_id}/{approval_id}` endpoint drive it unchanged.

Do not introduce a parallel event vocabulary the UI cannot render.

Rules:

- the live `cursor` orders emitted events;
- if Phase 0 gate 12 shows Hermes can redeliver events (at-least-once), add a
  bounded per-run seen-set keyed by Hermes event identity or
  `(runtimeRunId, sequence)` to drop duplicates; otherwise the cursor suffices;
- translate Hermes-native names inside `dataclaw_hermes/events.py`;
- a dropped Hermes stream fails the turn; it does not leave the run pending, and
  terminal state is written by the chat router, not by a Hermes-native terminal
  event.

Extend `RunTracker` with the status vocabulary in section 8.1 and external
correlation metadata. `RunTracker` remains the live event surface; durable
correlation lives in `runtime_runs.py`.

## 10. Provider selection and reload

### 10.1 Two-pass construction and the runtime bundle

The agent/LLM providers are built in `init_providers()` before plugins are
registered, so a factory invoked at that point cannot dispatch to
plugin-registered runtimes. Use this exact startup order:

1. **Direct defaults.** `init_providers()` builds the Direct/built-in bundle so a
   valid runtime always exists.
2. **Plugin registration.** Each external runtime plugin (OpenClaw, Hermes)
   registers a runtime **factory** with the registry. Registration MUST NOT
   replace the active provider.
3. **Plugin-default bootstrap.** `_bootstrap_plugin_defaults` writes plugin config
   defaults so `plugins.hermes.*` fields exist.
4. **Resolver refresh.** Invalidate/reload configuration so the selector sees
   current values.
5. **Selection pass.** Run the async selector.
6. **Publish active state.** Record `configured_runtime`, `active_runtime`, and
   `last_selection_error`, then publish the active bundle.

The selector returns an immutable **runtime bundle**, not a single provider:

```python
@dataclass(frozen=True)
class RuntimeBundle:
    agent: AgentProvider
    utility_llm: LLMProvider
    compaction: CompactionProvider
    tool_availability: ToolAvailability
    sub_agent_registry: SubAgentRegistry
    sub_agent_hooks: SubAgentHookRegistry
    memory: MemoryProvider
    system_prompt: SystemPromptProvider
    skill: SkillProvider
    hooks: HookRegistry                       # pre/post-tool + agent-message hooks; snapshot with providers
    runtime_control: RuntimeControl | None   # cancel/status; required for Hermes
    identity: RuntimeIdentity
    diagnostics: RuntimeDiagnostics
    availability: bool                        # False → an unavailable bundle that rejects turns

    async def aclose(self) -> None:
        # Cascade close to the components that own HTTP clients or resources.
        for component in (self.agent, self.utility_llm, self.runtime_control):
            close = getattr(component, "aclose", None)
            if close is not None:
                await close()


async def build_runtime_bundle(config, plugin_registry) -> RuntimeBundle:
    ...
```

- `openclaw` uses the registered OpenClaw factory.
- `hermes` uses the registered Hermes factory.
- Any other value (`anthropic | openai | gemini | codex | mock`) returns the
  existing Direct/built-in bundle — this is the "Direct" case.
- Missing plugins, invalid configuration, incompatible versions, and failed
  health checks raise typed errors.
- No external-runtime error silently returns Direct.

Shared core MUST NOT import a runtime plugin package directly (no import-based
factory) — selection is by registered factory only, so core stays
runtime-neutral. The registry MUST support runtime-factory registration
separately from active-provider replacement.

**Utility LLM.** The bundle's utility LLM — used by compaction and by
`DefaultSubAgentProvider`, which backs `delegate_to_subagent` — MUST be a real
configured model in Hermes mode and MUST satisfy the full `LLMProvider` contract
(streamed text plus tool calls; see gate 11), since sub-agents call tools.
Returning `MockLLM` for an external runtime would make delegation and compaction
ineffective. Phase 0 gate 11 found no usable raw utility endpoint in Hermes
0.19.0, so the runtime bundle always carries the globally configured DataClaw
utility model. DataClaw holds those credentials and delegated children run on
this utility LLM, not on Hermes or OpenClaw.

### 10.2 Reload and failure states

Track `configured_runtime`, `active_runtime`, and `last_selection_error`
independently.

1. Validate the proposed configuration.
2. Construct and health-check the new bundle through the selection pass.
3. Swap the whole bundle only after success.
4. On **startup failure**, keep the API/UI available but install an explicit
   unavailable provider that rejects turns with a typed error — never a silent
   Direct fallback. The rejection happens at `/agent` admission, **before** the
   user message is persisted or any compaction/tool resolution runs, so an
   unavailable runtime causes no session mutation.
5. On **reload failure**, retain the previous bundle and surface a prominent
   `configured ≠ active` unhealthy state with `last_selection_error`. New turns
   continue on the previous bundle (this is a retain-and-surface policy, not a
   fallback to Direct).
6. Retire a replaced bundle only after its last in-flight run releases it; on
   retirement call the bundle's optional `aclose()` to close HTTP clients and
   other resources. A bundle in use is never closed under an active run.

### 10.3 In-flight bundle

The chat router captures the whole runtime bundle in a local before a run and uses
that bundle — agent, utility LLM, compaction, tool availability, sub-agent registry
and hooks, memory, system prompt, skill, and the hook registry — for the entire
turn. Every provider and hook the loop reads mid-run is snapshotted, so a reload
cannot mix an old agent with a new LLM or a swapped provider. A reload rebuilds
providers and hooks **together**, so a snapshot is internally consistent — a
provider-bound hook such as `MemoryIngestHook(registry.memory)` or the
skill-refresh hook never calls a stale provider. Cancellation and status use the
runtime mapping captured on the run, not the current global selection.

**Process-local bundle lease.** A Hermes tool callback is a separate FastAPI task
and cannot inherit the chat task's contextvars, and the durable run record stores
only identifiers — not the Python bundle. The run therefore registers an
`ActiveRunContext` (holding the captured bundle) in a process-local
`runId → ActiveRunContext` map at run start. Tool search, tool call, status, and
cancellation resolve the bundle from this map by `runId`, then set
`current_runtime_bundle` (and the other contextvars) for the duration of the call
so delegation — which runs inside the callback task — reads the captured sub-agent
registry and hooks (closing the latent Direct-mode hole as well). The lease is
released only after terminalization **and** all outstanding callbacks finish; a
replaced bundle's `aclose()` runs after its lease is released (§10.2).

Bundle immutability is not run isolation. Some request-scoped state is not
task-local: the OpenAI provider's `prompt_cache_key` (mutable instance state the
loop overwrites per thread), and the workspace `_project_dir`, which a pre-tool
hook sets but stores **process-globally** — unlike the skill/subagent/dataset
allowlists, which were migrated to task-local contextvars. These race across
concurrent sessions today under Direct and OpenClaw alike; this is pre-existing,
runtime-agnostic debt, not Hermes-introduced. Concurrent runs sharing one bundle
MUST NOT race on such state: pass per-run settings as call arguments or use a
run-local wrapper, and prefer migrating `_project_dir` to a contextvar like its
siblings. A concurrent-session isolation test covers both `prompt_cache_key` and
`_project_dir`.

There is no session runtime stamp. The next turn uses the current active bundle
and receives Dataclaw's stored history.

## 11. Ordinary Hermes turn

### 11.1 Request

Before contacting Hermes, create the durable run record (§8.1) and validate the
correlation fields present in `AgentState` (it is `total=False`).

Send:

- a fresh opaque Hermes execution-session identifier;
- the complete turn input as `state.messages`, which already includes the
  just-persisted current user message — do **not** also send `state.user_query` as
  a separate message, or the current turn is duplicated;
- sanitized system and skill instructions;
- Dataclaw `run_id`/session/project correlation (validated);
- the configured Hermes model (§7.3);
- the restricted Dataclaw profile;
- the enabled tools, exposed through the Phase-0-verified mechanism (per-run
  filter, generic dispatch tool, or patch — §3.3 gate 10) and built from the one
  shared enabled-tool resolver (§12.1); disabled tools MUST be absent from the
  model-visible schema.

Do not:

- send `X-Hermes-Session-Key`;
- rely on Hermes memory;
- inject any tool beyond the enabled manifest;
- enable excluded native tools.

### 11.2 Stream

The adapter:

1. records opaque Hermes identifiers when returned (upsert into the run record);
2. parses only Phase 0 fixture-backed event shapes;
3. maps assistant text to `TextDeltaEvent`;
4. emits tool, progress, and usage events directly to the RunTracker (§9.1);
5. records usage separately;
6. ends the turn with `TurnCompleteEvent(skip_persist=False)`.

The chat router's terminalization helper persists exactly one terminal assistant
message on success. The adapter does not persist terminal state.

### 11.3 Terminalization

The chat router owns terminalization for all runtimes through one helper covering
success, failure, cancellation, and a duplicate terminal signal:

- **success** → persist exactly one assistant message (`skip_persist=False`),
  emit `run_finished`, finish the run;
- **failure / cancellation** → emit `run_error` (or the cancellation notice) and
  finish the run, with **no persisted terminal error message** — this matches
  Direct exactly, so Hermes does not diverge from existing history semantics;
- **duplicate terminal signal** → ignored idempotently.

There is no adapter-side stable terminal id, `terminalMessageId`, or terminal
digest in 3.5.

### 11.4 Disconnect, restart, stop, and cancellation

- On stream loss, the turn fails (the run transitions to failed or `unknown`).
  Dataclaw does not reconnect-and-replay a partially streamed Hermes turn in 3.5.
- On startup, persisted non-terminal Hermes runs are marked failed and never
  resumed.
- Stop transitions the run to `stopping`, aborts any pending approval waits for the
  run (resolved as denied, so no queued or approved-late tool executes), and calls
  the runtime-control protocol (`cancel(runtime_run_id)`) on the **captured**
  bundle/mapping, then reconciles to cancelled, completed, failed, or unknown via
  `status(runtime_run_id)`.
- Stop cancels the Hermes side but does **not** interrupt a Dataclaw tool callback
  already executing in its own task; that callback runs to completion and the lease
  releases afterward. This matches OpenClaw, whose proxy tools are likewise not
  interrupted by a stop (both cancel the loop task, not the callback task).
  Interrupting an in-flight local tool is a product-wide change, out of scope here.
- Approval and streaming continuity are process-lifetime only.

## 12. Dataclaw tool search and execution

These routes are part of the Hermes plugin, not a new globally authenticated core
API. They run in the same process as the chat router and share its in-memory
approval state (invariant 15).

### 12.1 Dataclaw tool search

```http
POST /api/hermes/tools/search
```

Request:

```json
{
  "runId": "Dataclaw run id",
  "sessionId": "Dataclaw session id",
  "projectId": "Dataclaw project id",
  "query": "search phrase",
  "limit": 8
}
```

Response:

```json
{
  "tools": [
    {
      "name": "canonical.tool",
      "summary": "short description",
      "inputSchema": {}
    }
  ]
}
```

This is a Dataclaw-side convenience endpoint, not Hermes-native progressive
disclosure. Like the call route (§12.2), the search route validates `runId`,
`sessionId`, and `projectId` and resolves tools through the **captured bundle's**
tool availability (correctness, not authentication). The enabled tools reach Hermes
through the Phase-0-verified tool-exposure mechanism (§3.3 gate 10); it and these
search results MUST be built from **one shared enabled-tool resolver**
(`providers.tool_availability.resolve_tools(state)` or its current equivalent) so
their schemas cannot drift. Search results are advisory; the call endpoint resolves
the tool again.

A search that returns no match MUST fall back to the full enabled-tool list for
the correlated session rather than an empty result, so a search miss never
silently removes an available tool. At ~70 tools this is a deliberate
correctness-over-disclosure choice.

### 12.2 Tool call

```http
POST /api/hermes/tools/{tool_name}/call
```

Request:

```json
{
  "runtimeRunId": "opaque Hermes run id",
  "toolCallId": "stable Hermes call id",
  "runId": "Dataclaw run id",
  "sessionId": "Dataclaw session id",
  "projectId": "Dataclaw project id",
  "params": {}
}
```

The handler:

1. resolves the run mapping and the process-local bundle lease by the stable
   Dataclaw `runId` (the primary correlation key), upserting the `runtimeRunId` on
   first sight, and locates the `RunState` requiring `run.run_id == request.runId`
   (not merely a matching session) with the session and project agreeing (routing
   correctness);
2. acquires the in-process `(runtimeRunId, toolCallId)` lock/future and **looks
   up** the idempotency record — it does not create one yet;
3. if a record exists: rejects a changed tool name or argument digest, then
   resolves the duplicate against **every** state — a terminal record
   (`completed`/`denied`/`failed`/`unknown`) returns its stored envelope; any
   in-flight record (`received`/`waiting_approval`/`approved`/`executing`) awaits
   the first call's shared future rather than starting a second invocation, and a
   `waiting_approval` duplicate reattaches to the existing approval instead of
   creating a second — all **before** any status gate, so a retry is race-safe
   regardless of the run's current status;
4. if no record exists, this is a **new** call: enforces an admissible run status —
   accept only while the run is `running` or `waiting_approval`; `stopping`,
   `completed`, `failed`, `cancelled`, or `unknown` reject without execution (a
   finished run lingers in `RunTracker` for its TTL). A rejected new call leaves no
   stray `received` record;
5. creates the idempotency record (canonical-JSON argument hash) only after
   admission;
6. resolves the enabled tool through the leased bundle's tool availability (the
   shared enabled-tool resolver);
7. acquires the per-run execution lock (serializing distinct concurrent calls),
   then **re-checks admissible run status** — waiting on the lock is a window in
   which the run may have been stopped or cancelled; if it is no longer live, abort
   without executing — and enters a context manager that sets `current_thread_id`,
   `current_emitter`, and `current_runtime_bundle` (from the lease), always
   resetting them in `finally`;
8. builds the existing tool-call state shape;
9. runs the leased bundle's **complete** `preToolCallHook` chain — not only
   guardrails — because the capability filters it also runs (subagent, dataset, and
   skill allowlists) set task-local, security-boundary contextvars that must be
   established in this callback task;
10. honors guardrail denial and user-approval modes (§12.3);
11. emits start, arguments, progress, result, and failure events;
12. invokes the existing Dataclaw callable;
13. runs the leased bundle's `postToolCallHook` chain;
14. persists the existing session tool-call message shape;
15. stores and returns the result.

Correlating on the stable Dataclaw `runId` (present in the body, backed by the
run record created before contact in §11.1) avoids a write-before-read race: a
tool callback may arrive before the streaming path has recorded the
`runtimeRunId`. Phase 0 gate 8 proves Hermes echoes this correlation.

The contextvars are required because `delegate_to_subagent` reads
`current_thread_id` / `current_emitter` for progress and conversation persistence;
without them, delegated progress and `conversation_id` follow-ups silently
degrade (the current OpenClaw proxy has this latent gap). The context manager
guarantees they reset even on exception.

Delegation is not special-cased: `delegate_to_subagent` is one of the enabled
Dataclaw tools and executes through this same path. Do not import or call
OpenClaw's proxy implementation.

**Serialized execution (Direct parity).** Hermes may issue multiple distinct tool
calls concurrently, but Dataclaw tracks a single active tool and one approval at a
time. 3.5 serializes all Dataclaw tool callbacks per Hermes run behind a per-run
execution lock (step 7): distinct concurrent calls run one at a time, matching
Direct's effectively-sequential turn and avoiding races on run status, progress,
persistence, and approval. Multi-tool tracking with an aggregate approval count is
deferred. A test exercises two distinct concurrent calls, including approval and
cancellation.

**Callback request scope.** Because the callback runs in its own task, it MUST
re-establish the full request scope from the lease: the bundle's providers and
hooks (not the global registry), the **complete** pre- and post-tool hook chains
(including the capability filters, which are security boundaries), the contextvars
(step 7), and `tool_progress_context`. Running only guardrails, or the global
hooks, would bypass capability filtering or use stale providers. The OpenClaw proxy
already runs the full hook chain; the only Hermes change is sourcing providers and
hooks from the captured bundle rather than the live global registry.

**Re-validate after every wait.** Acquiring the idempotency future, the execution
lock, and the approval event are all suspension points at which the run or record
state can change. The handler MUST re-check admissible run status after each before
executing and MUST NOT execute a tool whose run became terminal while it waited.
This is the shared invariant behind steps 3, 4, and 7 and the cancellation-safe
approval (§12.3) — a tool must never execute after its run is stopped or cancelled,
whether it was queued on the execution lock or waiting for approval.

### 12.3 Approval

For user approval, the handler reuses the existing in-memory mechanism verbatim:

1. create an `approval_id` and register `run.guardrail_approvals[approval_id]` on
   the `RunState` — the same map the Direct loop uses;
2. persist `waiting_approval` and the `approval_id` on the tool-call record;
3. emit the existing `guardrail:approval_required` custom event;
4. await the same `asyncio.Event`, released by
   `POST /agent/guardrail/{thread_id}/{approval_id}` — the existing endpoint and
   UI, unchanged;
5. on approval, persist `approved` and continue the same call;
6. on denial or timeout, persist `denied` and return a correlated tool error.

Because the approval primitive is an in-memory `asyncio.Event`, the bridge routes
MUST run in the same process as the chat API, and approval works only for the
process lifetime. `plugins.hermes.tool_callback_timeout_seconds` MUST exceed the
Dataclaw approval window plus a safety margin (startup validates this); if Phase 0
gate 9 shows Hermes caps the callback timeout below the window, shorten the
Dataclaw approval wait for the Hermes path to fit. No execution token is required.

Restart and drops:

- a run stopped or cancelled while a call awaits approval aborts that wait (the
  approval resolves as denied) and the tool does not execute; the approval wait
  re-checks run status on wake;
- restart during a pending approval marks the call `unknown`/failed and never
  auto-executes;
- a completed retry returns the stored result;
- an executing retry does not start a second invocation;
- an ambiguous call remains `unknown` until reconciled.

There is no cross-restart approval reattachment in 3.5.

Interaction with serialization: a distinct call queued behind one that is awaiting
approval waits on the execution lock and may exceed
`tool_callback_timeout_seconds`; it then relies on Hermes retrying the callback,
which is safe because the idempotency future/record dedupes it. Confirm in Phase 0
that Hermes retries timed-out tool callbacks; resolve this before enabling
long-running approvals alongside concurrent tools. It does not block initial
runtime scaffolding.

### 12.4 Trust statement

These endpoints have no authentication, matching the rest of Dataclaw. Run and
project comparisons prevent accidental correlation errors; they do not protect
against an attacker who can reach port 8000.

## 13. Model selection

- Use the model configured in §7.3 (profile main model or `plugins.hermes`
  override).
- Keep provider credentials outside prompts and events.
- Persist nothing route-specific on the run record (there is no `route` field).
- Fail a missing or invalid model before execution.
- Apply a changed model to new work only.
- Project Hermes usage into Runs.
- The required Dataclaw utility model (§10.1) backs delegated children via
  `DefaultSubAgentProvider`, not Hermes.

## 14. Native batch evaluation

Add a command that runs a versioned dataset through Hermes' native batch runner.
It is a non-blocking quality harness in 3.5, not a release gate.

Hermes 0.19.0's runner hard-codes `task_<index>` task IDs and creates no
Dataclaw sessions or Runs. The wrapper MUST report
`dataclawGovernanceCoverage: false`; it measures native Hermes quality only.
Governed Dataclaw tool, approval, and Runs behavior remains covered by adapter
integration tests rather than being falsely attributed to the native batch run.

Measure:

- task completion;
- native Hermes tool selection and argument validity;
- completion/partial state and API-call capture;
- latency and failure rate;
- cross-item isolation;
- partial failure and cancellation.

Emit machine-readable results. Do not use native batch as a shortcut around
normal Dataclaw tool, guardrail, approval, or Runs tests. Numeric regression
thresholds must be agreed before this harness may gate a release.

## 15. Setup, health, and diagnostics

Setup:

- install the Dataclaw adapter independently;
- install or verify pinned Hermes;
- install the Hermes Dataclaw extension;
- create or verify the restricted profile;
- run compatibility and health probes;
- show remediation without logging credentials.

Health states:

```text
not_installed
not_configured
configured_inactive
starting
healthy
unhealthy
incompatible
```

Diagnostics report:

- configured and active runtime, and last selection error;
- effective Hermes-side tool-callback timeout (as propagated to the extension);
- adapter and Hermes versions;
- compatibility fixture or patch version;
- API reachability;
- restricted-profile verification;
- unresolved run count;
- last sanitized error;
- local/private-use warning for non-loopback or Docker-published configurations.

## 16. Local/private trust requirements

The implementation MUST accurately document and preserve these facts:

- Dataclaw has no authentication layer.
- Anyone who can reach port 8000 can access data and execute enabled tools.
- Workspace shell and notebooks execute with host-process permissions.
- Credentials remain plain text in the Dataclaw config file.
- Direct startup defaults to `127.0.0.1`.
- Docker-published port 8000 must be restricted by host binding, firewall, or
  trusted private-network controls.
- HTML preview sandboxing does not sandbox tool execution.

Do not describe Hermes correlation checks as authentication or authorization.

Correctness checks still include:

- run/session/project/runtime correlation and `run_id`-matched callback attachment;
- enabled-tool resolution;
- guardrail and approval enforcement;
- argument-digest conflict detection;
- call idempotency and concurrency;
- bounded event, query, and argument sizes;
- credential redaction from logs and events;
- disabled Hermes-native tool verification.

Do not add a bridge token while the rest of the Dataclaw API remains
unauthenticated. If Dataclaw later adds a global security layer, migrate Hermes
routes to it rather than designing a separate scheme.

## 17. Implementation phases

### Phase 0 — Compatibility fixtures

Deliver:

- version pin;
- fixtures;
- compatibility tests (including gates 8–12: correlation round-trip, callback
  timeout headroom, tool-exposure mechanism, utility completion endpoint, event
  redelivery determination);
- patchset if required;
- restricted-profile proof.

Gate: every section 3.3 test passes.

### Phase 1 — Runtime core

Deliver:

- provider factory returning a runtime bundle, and two-pass registration in the
  §10.1 order;
- startup/reload convergence with the retain-and-surface failure policy;
- per-run bundle snapshotting;
- `run_id` and project scope in `AgentState` with boundary validation; real
  utility LLM in Hermes mode;
- the chat-router terminalization helper;
- structured events and extended Runs state;
- runtime and tool-call idempotency store with the concurrency primitive.

Gate: Direct and OpenClaw selection, chat, reload, and terminalization regressions
pass; the Hermes utility path does not resolve to `MockLLM`.

### Phase 2 — Hermes provider and tools

Deliver:

- adapter, client, and event translation with chat-router terminal ownership;
- required configured Dataclaw utility LLM;
- Dataclaw tool-search and tool-call routes and extension (in-process, shared
  resolver, contextvar CM, `run_id`-matched attachment);
- ordinary streaming and health;
- stop and best-effort cancellation via the runtime-control protocol;
- contextvar-scoped tool execution with hooks, approvals, events, persistence, and
  concurrency-safe idempotency;
- the single configured Hermes model.

Gate: ordinary, tool, approval, denial/timeout, failure, cancellation,
duplicate-call, and concurrent-duplicate tests pass.

### Phase 3 — Product and release

Deliver:

- setup and diagnostics;
- UI;
- native batch evaluation (non-blocking);
- documentation;
- package and lockfile changes;
- full regression and packaging tests.

Gate: the definition of done passes.

## 18. Required tests

### 18.1 Unit

- config validation and runtime selection;
- two-pass registration in the §10.1 order selects the correct bundle per backend;
- provider construction, failure, and reload (startup-failure unavailable
  provider; reload-failure retain-and-surface);
- unavailable runtime rejects at `/agent` admission with no session mutation;
- Codex-login hot reload routes through the centralized selector;
- runtime bundle snapshot: a mid-run reload does not change the LLM/compaction the
  turn uses;
- delegation resolves its sub-agent registry from the captured bundle, unaffected
  by a mid-run reload;
- concurrent-session isolation: two runs sharing a bundle do not race on
  per-request state (`prompt_cache_key` or the workspace `_project_dir` global);
- run-status and tool-call transition validity: terminal states are immutable and
  non-executable; invalid transitions are rejected;
- bundle retirement: a replacement does not close an in-use bundle; the last
  release calls `aclose()` exactly once; repeated reloads do not leak clients;
- Hermes utility LLM resolves to a real model, never `MockLLM`, and satisfies the
  full contract (streamed tool calls);
- terminalization helper: success persists one assistant message; failure and
  cancellation are event-only (no persisted error message); duplicate terminal
  signal is idempotent;
- runtime mapping serialization and revision conflict;
- every Phase 0 event fixture;
- tool call ID and canonical argument-digest conflict;
- concurrent duplicate tool call awaits/returns the first result;
- tool-call result envelope and per-state retry (completed/denied/failed/executing/
  unknown); failed and denied retries never re-execute;
- a new tool call after the run is terminal (or during `stopping`) is rejected
  without execution;
- callback-timeout validation against the approval window;
- guardrail allow, deny, approval, and timeout;
- model selection and failure.

### 18.2 Contract

- exact Hermes stream parsing;
- correlation round-trip on the tool callback;
- Dataclaw tool search request, response, correlation validation, and empty-result
  fallback;
- disabled tools are absent from the model-visible tool schema (prove absence, not
  just that enabled tools are present);
- tool-call request and response;
- approval pending and continuation;
- duplicate and conflicting tool calls.

### 18.3 Integration

- Direct runtime selection and chat regression;
- OpenClaw runtime selection and chat regression;
- Hermes ordinary stream with chat-router terminal persistence;
- Dataclaw tool search and tool execution;
- approval, denial, timeout, and retry;
- delegation through the existing `delegate_to_subagent` tool under Hermes,
  including a `conversation_id` follow-up (contextvars set), running on the
  utility LLM;
- model selection and failure;
- disconnect fails the turn (no reconnect-replay);
- restart marks non-terminal runs failed with no auto-resume or auto-execute;
- hot reload during an active run does not swap the in-flight bundle, and
  provider-bound hooks stay consistent with the snapshotted providers;
- a tool callback resolves the captured bundle from the lease across the FastAPI
  task boundary, and delegation uses it;
- SSE continuity, cancellation, and second-turn admission during `waiting_approval`
  and `stopping` (these statuses are treated as live);
- two distinct concurrent Hermes tool calls are serialized, including one awaiting
  approval while another completes, and cancellation;
- a tool call does not execute after its run is stopped/cancelled — whether queued
  on the execution lock or awaiting approval (status re-validated after every wait);
- duplicate calls in `received`/`waiting_approval`/`approved`/`executing` await the
  shared future or reattach to the approval, never double-executing;
- the current user message reaches Hermes exactly once — after compaction and for
  identical consecutive prompts;
- late callback with a stale `runId` does not attach to a newer run;
- switching runtime between turns on an existing Dataclaw session.

### 18.4 Correctness and trust-boundary

- mismatched run/session/project/runtime correlation;
- forged or unknown runtime identifiers;
- duplicate call with changed arguments;
- concurrent duplicate tool call;
- disabled native tool invocation;
- credential leakage scan;
- loopback defaults and non-loopback warning;
- cross-path Direct-vs-Hermes parity for the same tool + guardrail: identical
  allow, approval, denial, redaction, post-hook intervention, persistence, and
  delegation-follow-up outcomes;
- documentation contains the local/private-use warning.

### 18.5 Packaging and UI

- install Hermes without OpenClaw;
- install all three providers;
- disable or remove Hermes without breaking Direct/OpenClaw;
- configuration round trip;
- configured-versus-active and incompatible status;
- approval event rendering;
- production UI build.

After targeted phase tests, run:

```text
uv run pytest
npm run build
```

Do not weaken unrelated tests.

## 19. Definition of done

- The exact pinned compatibility suite passes, including the correlation
  round-trip, callback-timeout headroom, manifest-injection, utility-endpoint, and
  event-redelivery gates.
- Direct, OpenClaw, and Hermes are selectable through the two-pass selection pass;
  the factory returns a runtime bundle; plugins register factories and never
  replace the active provider.
- Core imports no runtime plugin package.
- Startup failure installs an unavailable provider that rejects turns; reload
  failure retains the previous bundle and surfaces `configured ≠ active`.
- Plugin registration cannot override `llm.backend`.
- Hermes initialization failure never silently selects Direct.
- In Hermes mode, compaction and `delegate_to_subagent` use the required
  configured Dataclaw utility LLM, never `MockLLM`; children run on the utility
  LLM, not on Hermes.
- In-flight runs retain their captured runtime bundle; a mid-run reload cannot
  change the LLM/compaction the turn uses.
- Existing Direct and OpenClaw tool behavior remains unchanged.
- Hermes tools use the leased bundle's availability and complete pre/post hook
  chains (including capability filters), guardrails, approvals, events, callables,
  and session persistence, with `current_thread_id` / `current_emitter` /
  `current_runtime_bundle` set and reset via a context manager.
- Delegation runs through the existing `delegate_to_subagent` tool with no
  Hermes-native delegation path, and `conversation_id` follow-ups work.
- Stable Hermes tool IDs, stored results, and the in-process concurrency lock
  prevent duplicate and concurrent-duplicate execution.
- Callbacks attach only to the matching `run_id`.
- The chat router's terminalization helper persists terminal content exactly once
  on success and keeps failures event-only, matching Direct; the adapter writes no
  terminal state.
- Dataclaw tool search returns only tools enabled for the correlated session, with
  a full-list fallback; tool exposure and search share one resolver; enabled tools
  reach Hermes through the Phase-0-verified mechanism, with disabled tools absent
  from the model-visible schema.
- The single configured Hermes model is enforced (profile main model or
  `plugins.hermes` override).
- Bridge routes run in-process; approval reuses the existing `guardrail_approvals`
  maps and `/agent/guardrail` endpoint; `tool_callback_timeout_seconds` exceeds the
  approval window.
- Cancellation uses the captured bundle/mapping and the runtime-control protocol
  (mandatory for Hermes).
- An unavailable runtime rejects at admission with no session mutation; the
  Codex-login reload routes through the selector.
- Delegated children resolve their sub-agent registry from the captured bundle
  (reached via the process-local lease across the callback task boundary);
  concurrent runs do not race on per-request provider state.
- New run statuses route through `is_live`/`is_terminal`; SSE, cancellation, and
  second-turn admission handle `waiting_approval` and `stopping`.
- Distinct concurrent Hermes tool calls are serialized per run.
- Disabled tools are absent from the model-visible schema (mechanism recorded in
  Phase 0); the current user message reaches Hermes exactly once.
- The bundle snapshots the hook registry; provider-bound hooks never call stale
  providers after reload.
- No tool call executes after its run is terminal; run and tool-call terminal
  states are immutable and non-executable per the transition tables; a terminal
  idempotency record is returned before any status gate.
- No tool executes after its run is stopped or cancelled, including calls queued on
  the execution lock or awaiting approval; the handler re-validates status after
  every wait, and stop aborts pending approvals.
- The tool-search route validates run/session/project and uses the captured
  bundle's tool availability; bundle retirement closes clients exactly once.
- `RuntimeBundle` is a formal frozen type with the fields in §10.1 (including
  `sub_agent_registry`, `sub_agent_hooks`, `runtime_control`, `availability`, and
  `aclose`).
- The utility LLM satisfies the full `LLMProvider` contract (streamed tool calls),
  and `llm.backend` plus `llm.<provider>.model` configure it once for every
  runtime.
- `tool_callback_timeout_seconds` is propagated into the Hermes extension and
  reported in diagnostics.
- The tool-call result envelope and per-state retry are enforced; identical
  failed/denied retries never re-execute; replaced bundles close via `aclose()`
  after their last run.
- The restricted profile contains none of the excluded native tools.
- Hermes has no OpenClaw dependency.
- UI, diagnostics, and packaging gates pass; native batch evaluation runs and
  reports (non-blocking).
- The UI and documentation repeat the local/private-use warning.
- No claim suggests that Hermes bridge routes add authentication or sandboxing.
