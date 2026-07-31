# Hermes Runtime Plan

**Status:** Implemented; live pinned-runtime validation remains a release gate  
**Release target:** Dataclaw 3.5  
**Implementation contract:** [Hermes Runtime Implementation Specification](hermes-runtime-implementation-spec.md)

## Objective

Add Hermes Agent as a first-class Dataclaw runtime alongside DataClaw and
OpenClaw. Runtime selection and the shared DataClaw utility model are separate:

```yaml
agent:
  runtime: dataclaw | openclaw | hermes
llm:
  backend: anthropic | openai | gemini | codex
```

`agent.runtime: dataclaw` runs the primary agent with the selected utility
model. `openclaw` and `hermes` own their primary agent loops but receive the
same DataClaw utility model for compaction and delegated sub-agents.

Hermes must be independently installable. It must not import, invoke, or require
the Dataclaw OpenClaw plugin, OpenClaw tools, or an OpenClaw process.

Dataclaw remains the product surface and source of conversation history, tool
configuration, approvals, and Runs visibility. Hermes owns the agent loop when
selected.

## Product decisions

1. A Dataclaw installation may contain all three runtime adapters.
2. `agent.runtime` selects the primary runtime globally. `llm.backend` always
   selects DataClaw's shared utility provider.
3. Configuration reload may change the runtime for subsequent turns.
4. Sessions are not pinned to a runtime in 3.5. A subsequent turn uses the
   currently selected runtime. The Hermes adapter receives existing Dataclaw
   conversation history explicitly; current OpenClaw behavior is unchanged.
5. An in-flight run retains the provider instance with which it started.
6. Provider initialization failure is visible. Dataclaw must not silently fall
   back to Direct.
7. The chat router remains the sole writer of terminal assistant messages for all
   runtimes, including Hermes.
8. Hermes runs within Dataclaw's existing local/private trust model. The
   integration does not add a separate authentication, TLS, or sandbox boundary.

## Release 3.5 scope

Hermes mode includes:

- ordinary chat turns;
- structured run lifecycle and streamed events;
- Dataclaw tool discovery through the Phase-0-verified tool-exposure mechanism,
  plus an optional Dataclaw-side tool-search endpoint;
- Dataclaw tool execution through a Hermes-specific local bridge;
- Dataclaw approval and guardrail handling reusing the existing in-memory
  approval mechanism;
- a single configured Hermes model (profile main model or override);
- delegation through Dataclaw's existing sub-agent tool, called as a governed
  tool — not a Hermes-native delegation runtime;
- stop and best-effort cancellation;
- native Hermes batch evaluation as a non-blocking quality harness;
- configuration, setup, health, diagnostics, packaging, and UI support.

Not part of 3.5 (see **Deferred capabilities**): persistent goals, Hermes
long-term memory, Hermes-native structured delegation, Dataclaw-owned scheduled
jobs, the policy-based model-route engine, adapter-owned terminal persistence,
durable approval recovery, and cross-restart event replay.

## Architecture

### Ownership

| Concern | Dataclaw | Hermes |
|---|---|---|
| Runtime selection | Owns global selection | Executes when selected |
| Conversation history | Canonical store | Receives explicit context |
| Terminal message | Chat router is sole writer | Streams text, no terminal write |
| User-visible run state | Canonical projection | Emits execution events |
| Tools and skills | Catalog, availability, hooks, approval, execution, persistence | Discovers and requests |
| Model selection | Configures one Hermes model | Uses the configured model |
| Delegation | Owns the existing sub-agent tool and its policy | Calls it as a governed tool |
| Runtime memory and learning | Disabled for 3.5 | Does not mutate |

Hermes does not become a second policy or conversation store.

### Runtime topology

The integration has three layers:

1. **Small shared Dataclaw runtime core**
   - centralized provider selection through a two-pass startup sequence;
   - structured external-runtime events;
   - durable runtime identity mappings;
   - Runs projection.
2. **Dataclaw Hermes adapter**
   - `AgentProvider`;
   - Hermes API client and event translation;
   - Hermes-specific tool/search routes (in-process with the chat API);
   - setup, health, and plugin registration.
3. **Hermes Dataclaw extension**
   - Dataclaw tool-search adapter;
   - Dataclaw tool handler;
   - stable correlation identifiers.

Shared Dataclaw core has no Hermes SDK dependency and imports no runtime plugin
package.

## Dataclaw-side changes beyond handoff calls

| Area | Current behavior | Required 3.5 change |
|---|---|---|
| Provider selection | Startup constructs providers before plugins register; plugins replace the agent provider imperatively | Two-pass sequence returning an immutable runtime bundle, in the exact order default → register → bootstrap → resolve → select → publish |
| Selection failure | No configured/active/error separation; no failure contract | Track configured/active/last-error separately; startup failure installs an unavailable provider that rejects turns; reload failure retains the previous bundle and surfaces `configured ≠ active` |
| Utility LLM | External runtimes previously inherited a provisional `MockLLM` | Require one shared `llm.backend` provider/model for DataClaw utilities in every runtime; delegated children run on that utility LLM, not Hermes or OpenClaw |
| Agent state | `AgentState` carries no `run_id` or project scope | Add `run_id` and project scope, validated at the boundary (`total=False`) |
| In-flight runs | The loop reads `providers.llm`/compaction/tool-availability/hooks fresh mid-run | Capture the whole bundle (providers + hooks) at run start, reachable by callbacks via a process-local `runId → ActiveRunContext` lease; isolate per-request provider state across concurrent runs; close a replaced bundle via `aclose()` after its last run |
| Terminalization | The router persists on success but not on failure; each runtime terminates ad hoc | One chat-router terminalization helper (success persists; failure/cancel event-only, matching Direct; duplicate ignored) |
| Runtime identity | External runtime IDs do not have one durable mapping model | Create the run record keyed by the Dataclaw run id before contacting Hermes; upsert opaque Hermes IDs on arrival |
| Broker events | Current event types cover Direct's basic text/tool loop | Add progress, usage, cancellation, and failure events, emitted as existing emitter strings |
| Runs lifecycle | Live tracking is process-local; only literal `running` is treated as active | Add external-runtime statuses with an allowed-transition table (terminal immutable) and shared `is_live`/`is_terminal` helpers (audit SSE, cancellation, second-turn admission); serialize distinct tool calls per run; reject tool calls after terminal state; a `cancel`/`status` control protocol on the captured bundle; the chat router stays the terminal writer (no adapter terminal store, no watermark replay) |
| Hermes tools | No Hermes callback path exists | Add a Hermes-specific local tool router that reuses Dataclaw tool availability, hooks, approvals, execution, events, and session persistence, and sets the request contextvars |
| Model | Runtime model choice is not configured for Hermes | Configure one Hermes model (profile main model or `plugins.hermes` override); no route engine |
| Operations | No Hermes install or health surface exists | Add configuration, setup, compatibility checks, diagnostics, packaging, UI, and a non-blocking batch-evaluation command |

The following do not change in 3.5:

- Direct tool orchestration;
- the OpenClaw tool proxy;
- the existing sub-agent delegation tool and its policy;
- Dataclaw's lack of API authentication;
- the conversation and session storage model;
- existing tool implementations, skill registry, and policy hooks;
- credential storage;
- shell and notebook execution permissions.

There is no shared cross-runtime tool-executor migration or database migration in
this release.

## Execution handoffs

### Ordinary turn

1. Dataclaw resolves and snapshots the whole runtime bundle for the run.
2. Dataclaw creates the durable run record, keyed by the Dataclaw run id, before
   contacting Hermes.
3. The Hermes adapter sends the complete turn input (`state.messages`, which
   already includes the current user message — not history plus a duplicate input),
   the configured model, correlation identifiers (including the Dataclaw `run_id`,
   validated), and the restricted Dataclaw profile.
4. Hermes runs the agent loop and streams structured events; opaque Hermes IDs are
   upserted into the run record as they arrive.
5. Dataclaw translates and publishes those events; the adapter maps text to
   `TextDeltaEvent` and ends with `TurnCompleteEvent(skip_persist=False)`.
6. The chat router's terminalization helper persists exactly one assistant message
   on success; failures are event-only, matching Direct. The adapter does not
   persist terminal state.

Ordinary turns use a fresh opaque Hermes execution session. The adapter does not
send `X-Hermes-Session-Key`; Dataclaw history remains canonical.

### Tool search and tool execution

1. Hermes learns the enabled Dataclaw tools through the Phase-0-verified
   tool-exposure mechanism (per-run filter, generic dispatch tool, or patch — with
   disabled tools absent from the model-visible schema), and may re-query them
   through the Dataclaw tool-search endpoint.
2. Search results are filtered using the session's enabled tools and capability
   context. If a search returns nothing, the extension falls back to the full
   enabled-tool list so a search miss never silently disables a tool.
3. Hermes calls the selected Dataclaw tool with a stable `tool_call_id` and
   Dataclaw run/session/project correlation.
4. The Hermes router loads the run mapping by the Dataclaw run id and verifies the
   correlation agrees.
5. It sets `current_thread_id` and `current_emitter`, resolves the tool through
   Dataclaw's existing availability service, and runs existing pre-tool hooks.
6. A guardrail denial returns a correlated tool error.
7. A user-approval decision reuses the existing in-memory approval maps and the
   existing `/agent/guardrail` endpoint; the tool call waits for that decision
   while the process is alive.
8. On approval, the router invokes the existing Dataclaw tool callable, emits
   progress and result events, runs post-tool hooks, persists the tool message,
   and resets the contextvars.
9. A retry with the same run and call identifier returns the stored result rather
   than executing again.

This is a Hermes-specific orchestration path modeled on the current OpenClaw
proxy. It reuses Dataclaw primitives but does not import OpenClaw code.

Delegation is one of these governed tools: Hermes invokes Dataclaw's existing
`delegate_to_subagent` tool through the same route. There is no Hermes-native
child-admission path in 3.5.

## Local/private trust boundary

The Hermes integration inherits Dataclaw's documented security model:

- the API has no authentication;
- credentials are stored as plain text;
- shell and notebook tools execute with host-process permissions;
- direct startup binds to `127.0.0.1` by default;
- Docker-published port 8000 is network-accessible unless restricted externally.

The Hermes callback routes therefore do not add a bridge-only authentication
scheme in 3.5. A bridge token would not secure the rest of the unauthenticated
Dataclaw API.

The bridge routes run in the same process as the chat API, because the approval
mechanism is an in-memory event and the correlation state is process-local.

Correlation checks, approval state, stable call IDs, and retry deduplication remain
required for correctness. They are not presented as authorization controls.

Hermes and Dataclaw must run on the same host or a trusted private network. Do not
expose either API to an untrusted network. If Dataclaw later adds global
authentication, TLS, or sandboxing, the Hermes routes must adopt that shared
boundary.

## Relationship to OpenClaw

Hermes matches the OpenClaw provider at the Dataclaw product boundary:

- global `agent.runtime` selection;
- a shared DataClaw utility provider under `llm.backend`;
- Dataclaw-owned history;
- a runtime adapter and callback/tool routes;
- Runs events and chat-router terminal persistence;
- Dataclaw tool availability and hooks.

Hermes remains independent:

- no OpenClaw gateway;
- no OpenClaw session tools;
- no OpenClaw memory files;
- no import or call into the OpenClaw plugin;
- no OpenClaw-specific credentials or skills.

The OpenClaw tool proxy is not migrated in 3.5. OpenClaw does receive the shared
DataClaw utility model for compaction and delegated sub-agents.

Hermes 3.5 will not provide OpenClaw-native memory, session-management semantics,
gateway/channel behavior, or OpenClaw plugin compatibility.

## Hermes-specific value

Hermes adds, in 3.5:

- an optional Dataclaw-side tool-search endpoint as a context optimization (the
  Phase-0-verified mechanism remains the default tool-presentation path);
- native batch evaluation for runtime quality and regressions;
- correct delegation context (contextvars set on the tool route), which the
  current OpenClaw proxy does not do.

Hermes' native structured delegation, policy model routes, native Tool Search, and
native background execution are deferred (see **Deferred capabilities**); 3.5
reuses Dataclaw's existing delegation tool and a single configured model.

## Required Hermes compatibility gates

Phase 0 fixtures against the pinned Hermes version must prove:

1. stable streaming for text, tool, progress, usage, completion, failure, and
   cancellation;
2. a stable `tool_call_id` reaches the Dataclaw handler;
3. a Dataclaw tool call may remain pending while approval is collected and then
   receive its correlated result;
4. stop and reconnect distinguish running, completed, failed, cancelled, and
   unknown;
5. disabled native tools can be excluded from the Dataclaw Hermes profile;
6. the pinned package and required features are distributable;
7. Dataclaw-supplied correlation (`runId`/`sessionId`) is echoed back on the tool
   callback;
8. the tool-callback client timeout can be configured above the Dataclaw approval
   window (or its cap is recorded so the window can be shortened);
9. the session's enabled tools reach Hermes through a concrete supported mechanism
   (per-run filter, generic dispatch tool, or patch) with disabled tools absent
   from the model-visible schema;
10. a Hermes model endpoint satisfies the full `LLMProvider` contract utility work
    needs (streamed text and tool calls), or a Dataclaw fallback utility model is
    recorded;
11. whether Hermes can redeliver stream events, determining whether event
    deduplication is needed.

Specification §3.3 is the authoritative gate list (12 numbered gates); this
summary groups them.

If a required contract is absent, prefer a supported Hermes extension point. A
small version-pinned patch is acceptable only when it has fixture tests and a
clear removal path. Do not approximate a lifecycle or approval guarantee through
prompting.

## Delivery sequence

### Phase 0 — Compatibility freeze

- pin Hermes;
- capture API, stream, tool, approval-pending, correlation-echo, and
  manifest-injection fixtures;
- prove the compatibility gates;
- document the minimal patchset, if any.

### Phase 1 — Runtime core

- centralize provider selection through the two-pass sequence;
- register runtime factories without replacing the active provider;
- add `run_id`/project scope to `AgentState`; back the Hermes utility LLM with a
  real model;
- snapshot providers for in-flight runs;
- add structured events and runtime mappings;
- preserve Direct and OpenClaw behavior.

### Phase 2 — Hermes provider and tools

- add the Dataclaw Hermes adapter and Hermes extension;
- implement streaming with chat-router terminal ownership, health, stop, and
  best-effort cancellation;
- implement Dataclaw tool search and the Hermes-specific governed tool route with
  contextvars;
- implement approvals reusing the existing mechanism and the single configured
  model.

### Phase 3 — Product and release

- add setup, diagnostics, configuration, and UI;
- add native batch evaluation (non-blocking);
- complete contract, integration, regression, recovery, and packaging tests.

## Release gates

Dataclaw 3.5 may ship Hermes mode only when:

- Phase 0 fixtures pass against the exact pinned Hermes version;
- Direct and OpenClaw runtime-selection regressions pass;
- the two-pass selection pass returns a runtime bundle, picks the right runtime,
  and plugin registration cannot switch an in-flight or active provider by itself;
- startup-selection failure rejects turns via an unavailable provider; reload
  failure retains the previous bundle and surfaces `configured ≠ active`;
- the Hermes utility LLM resolves to a real model, never `MockLLM`, and delegated
  children run on it;
- provider reload cannot switch the captured bundle of an in-flight run
  (LLM/compaction included);
- tool availability, guardrails, approval, hooks, events, and persistence work
  through the Hermes route with contextvars set and reset;
- duplicate or concurrent Hermes tool calls do not execute twice, and a callback
  attaches only to its matching run id;
- the tool-callback timeout exceeds the approval window, and cancellation uses the
  captured bundle;
- callbacks resolve the captured bundle via the process-local lease; SSE,
  cancellation, and admission handle `waiting_approval`/`stopping`; distinct tool
  calls are serialized per run;
- disabled tools are absent from the model-visible schema; the current user message
  reaches Hermes exactly once;
- the chat router persists terminal output exactly once on success; failures stay
  event-only, matching Direct;
- the restricted Hermes profile exposes no disabled native tool;
- Hermes installation and removal do not require OpenClaw;
- UI and diagnostics report configured, active, unhealthy, and incompatible
  runtime states accurately;
- native batch evaluation runs and emits machine-readable results (non-blocking;
  numeric regression thresholds must be agreed before it can gate a release);
- documentation repeats the local/private-use warning.

## Deferred capabilities

- Hermes-native structured delegation (parent/child admission, depth and fan-out
  control); 3.5 reuses the existing `delegate_to_subagent` tool;
- Dataclaw-owned scheduled jobs and background dispatch through Hermes;
- the policy-based model-route engine (per-work-kind aliases and budgets); align
  with the planned Sprint-2 OpenRouter per-sub-agent routing;
- native Hermes Tool Search (deferrable-tool progressive disclosure); 3.5 uses
  the Phase-0-verified tool-exposure mechanism;
- adapter-owned terminal persistence, stable terminal IDs, durable approval
  recovery, and cross-restart event-watermark replay;
- persistent goals and goal-scoped long-running sessions;
- Dataclaw-backed Hermes long-term memory and learning;
- a canonical tool service shared by Direct, OpenClaw, and Hermes;
- authentication, TLS, and sandboxing as a Dataclaw-wide security boundary;
- per-session runtime pinning, adoption, and forking;
- session forks and context-engine variants;
- governed Kanban projection;
- reviewed memory or skill proposals;
- governed programmatic tool composition through `execute_code`;
- multiple Hermes profiles;
- inline image transport;
- Honcho or Curator integration.

## Hermes references

- [Hermes Agent documentation](https://hermes-agent.nousresearch.com/docs)
- [API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/)
- [Hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks/)
- [Tool Search](https://hermes-agent.nousresearch.com/docs/user-guide/features/tool-search)
- [Delegation](https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation/)
- [Persistent goals](https://hermes-agent.nousresearch.com/docs/user-guide/features/goals)
- [Batch processing](https://hermes-agent.nousresearch.com/docs/user-guide/features/batch-processing)
- [Profiles](https://hermes-agent.nousresearch.com/docs/user-guide/profiles/)
- [Memory](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/)
- [Configuring models](https://hermes-agent.nousresearch.com/docs/user-guide/configuring-models)
