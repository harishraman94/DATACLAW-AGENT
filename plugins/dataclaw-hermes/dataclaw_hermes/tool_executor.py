"""Governed Dataclaw tool execution for Hermes callbacks."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from fastapi import HTTPException, Request

from dataclaw.api.context import (
    current_emitter,
    current_runtime_bundle,
    current_thread_id,
)
from dataclaw.api.run_tracker import get_run_tracker, is_live
from dataclaw.events.emitter import AgentEventEmitter
from dataclaw.pending_actions import (
    register_guardrail_action,
    resolve_guardrail_action,
)
from dataclaw.providers.tool.llm_redact import redact_for_llm
from dataclaw.storage import sessions
from dataclaw.storage.runtime_runs import (
    TOOL_TERMINAL,
    RuntimeRunStore,
    canonical_arguments_digest,
)
from dataclaw.tool_progress import tool_progress_context
from dataclaw_hermes.config import APPROVAL_WAIT_SECONDS

logger = logging.getLogger(__name__)


def _envelope(
    state: str,
    content: Any,
    *,
    is_error: bool,
    guardrail_id: str | None = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "isError": is_error,
        "content": content,
        "guardrailId": guardrail_id,
    }


@contextmanager
def _request_context(
    *,
    thread_id: str,
    emitter: AgentEventEmitter,
    bundle: Any,
) -> Iterator[None]:
    thread_token = current_thread_id.set(thread_id)
    emitter_token = current_emitter.set(emitter)
    bundle_token = current_runtime_bundle.set(bundle)
    try:
        yield
    finally:
        current_runtime_bundle.reset(bundle_token)
        current_emitter.reset(emitter_token)
        current_thread_id.reset(thread_token)


async def _load_correlated_context(
    request: Request,
    *,
    run_id: str,
    session_id: str,
    project_id: str | None,
) -> tuple[Any, dict[str, Any], Any]:
    store: RuntimeRunStore = request.app.state.runtime_run_store
    mapping = await store.get_run(run_id)
    if mapping is None or mapping.get("runtime") != "hermes":
        raise HTTPException(404, "Unknown Hermes run")
    if mapping.get("sessionId") != session_id:
        raise HTTPException(400, "Run/session correlation mismatch")
    if mapping.get("projectId") != project_id:
        raise HTTPException(400, "Run/project correlation mismatch")

    tracker = get_run_tracker()
    run = tracker.get_run(session_id)
    if run is None or run.run_id != run_id:
        raise HTTPException(404, "No matching live Dataclaw run")

    manager = request.app.state.runtime_manager
    ctx = manager.get_run(run_id)
    if ctx is None:
        raise HTTPException(404, "Runtime bundle lease is no longer active")
    return ctx, mapping, run


async def search_tools(
    request: Request,
    *,
    run_id: str,
    session_id: str,
    project_id: str | None,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    ctx, _mapping, run = await _load_correlated_context(
        request,
        run_id=run_id,
        session_id=session_id,
        project_id=project_id,
    )
    if not is_live(run.status):
        raise HTTPException(
            409, f"Run is not searchable (status={run.status})"
        )
    manager = request.app.state.runtime_manager
    async with manager.callback_scope(run_id):
        emitter = AgentEventEmitter(session_id, run_id)
        with _request_context(
            thread_id=session_id,
            emitter=emitter,
            bundle=ctx.bundle,
        ):
            state = {
                "run_id": run_id,
                "session_id": session_id,
                "project_id": project_id,
                "messages": [],
            }
            definitions, _ = (
                await ctx.bundle.tool_availability.resolve_tools(state)
            )
            needle = query.strip().lower()
            matches = [
                tool
                for tool in definitions
                if not needle
                or needle in str(tool.get("name", "")).lower()
                or needle in str(tool.get("description", "")).lower()
            ]
            if not matches:
                matches = definitions
            return [
                {
                    "name": tool.get("name", ""),
                    "summary": tool.get("description", ""),
                    "inputSchema": tool.get("parameters")
                    or {"type": "object", "properties": {}},
                }
                for tool in matches[: max(1, min(limit, 100))]
            ]


async def execute_tool_call(
    request: Request,
    *,
    runtime_run_id: str,
    tool_call_id: str,
    run_id: str,
    session_id: str,
    project_id: str | None,
    tool_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    ctx, mapping, run = await _load_correlated_context(
        request,
        run_id=run_id,
        session_id=session_id,
        project_id=project_id,
    )
    mapped_runtime_id = mapping.get("runtimeRunId")
    if not runtime_run_id:
        runtime_run_id = str(mapped_runtime_id or "")
    if not runtime_run_id:
        raise HTTPException(409, "Hermes runtime run id is not available")
    if mapped_runtime_id and mapped_runtime_id != runtime_run_id:
        raise HTTPException(400, "Runtime run correlation mismatch")
    if not mapped_runtime_id:
        await request.app.state.runtime_run_store.update_run(
            run_id, runtimeRunId=runtime_run_id
        )

    manager = request.app.state.runtime_manager
    async with manager.callback_scope(run_id):
        return await _idempotent_execute(
            request,
            ctx=ctx,
            run=run,
            runtime_run_id=runtime_run_id,
            tool_call_id=tool_call_id,
            run_id=run_id,
            session_id=session_id,
            project_id=project_id,
            tool_name=tool_name,
            params=params,
        )


async def _idempotent_execute(
    request: Request,
    *,
    ctx: Any,
    run: Any,
    runtime_run_id: str,
    tool_call_id: str,
    run_id: str,
    session_id: str,
    project_id: str | None,
    tool_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    store: RuntimeRunStore = request.app.state.runtime_run_store
    key = (runtime_run_id, tool_call_id)
    digest = canonical_arguments_digest(params)
    leader = False
    future: asyncio.Future[dict[str, Any]]

    async with ctx.idempotency_lock:
        record = await store.get_tool_call(runtime_run_id, tool_call_id)
        if record is not None:
            if (
                record.get("toolName") != tool_name
                or record.get("argumentsDigest") != digest
            ):
                raise HTTPException(
                    409,
                    "tool_call_id was reused with different arguments",
                )
            if record.get("state") in TOOL_TERMINAL:
                result = record.get("result")
                if record.get("state") == "unknown":
                    raise HTTPException(
                        409,
                        result
                        or "Tool execution outcome is unknown; it will not be retried",
                    )
                if isinstance(result, dict):
                    return result
                return _envelope(
                    str(record.get("state")),
                    result,
                    is_error=record.get("state") != "completed",
                )
            future = ctx.tool_futures.get(key)
            if future is None:
                # A non-terminal durable record without the process-local leader
                # can only be a restart/drop. Never guess that it is safe to run.
                unknown = _envelope(
                    "unknown",
                    "Tool execution lost its in-process leader and will not be retried",
                    is_error=True,
                )
                await store.update_tool_call(
                    runtime_run_id,
                    tool_call_id,
                    state="unknown",
                    result=unknown,
                )
                raise HTTPException(409, unknown)
        else:
            # New-call admission occurs before a durable received record exists.
            if run.status not in {"running", "waiting_approval"}:
                raise HTTPException(
                    409, f"Run is not executable (status={run.status})"
                )
            await store.create_tool_call(
                runtime_run_id=runtime_run_id,
                tool_call_id=tool_call_id,
                dataclaw_run_id=run_id,
                session_id=session_id,
                project_id=project_id,
                tool_name=tool_name,
                arguments_digest=digest,
            )
            future = asyncio.get_running_loop().create_future()
            ctx.tool_futures[key] = future
            ctx.tool_identities[key] = (tool_name, digest)
            leader = True

    if not leader:
        # Every non-terminal retry (received/waiting/approved/executing)
        # follows the first invocation's shared result future.
        return await asyncio.shield(future)

    try:
        result = await _execute_leader(
            request,
            ctx=ctx,
            run=run,
            runtime_run_id=runtime_run_id,
            tool_call_id=tool_call_id,
            run_id=run_id,
            session_id=session_id,
            project_id=project_id,
            tool_name=tool_name,
            params=params,
        )
    except asyncio.CancelledError:
        unknown = _envelope(
            "unknown",
            "The callback ended before the tool outcome was confirmed",
            is_error=True,
        )
        record = await store.get_tool_call(runtime_run_id, tool_call_id)
        if record and record.get("state") not in TOOL_TERMINAL:
            await store.update_tool_call(
                runtime_run_id,
                tool_call_id,
                state="unknown",
                result=unknown,
            )
        if not future.done():
            future.set_result(unknown)
        raise
    except HTTPException as exc:
        failure = _envelope(
            "failed",
            str(exc.detail),
            is_error=True,
        )
        record = await store.get_tool_call(runtime_run_id, tool_call_id)
        if record and record.get("state") not in TOOL_TERMINAL:
            await store.update_tool_call(
                runtime_run_id,
                tool_call_id,
                state="failed",
                result=failure,
            )
        if not future.done():
            future.set_result(failure)
        return failure
    except Exception as exc:
        logger.exception("Hermes tool execution failed: %s", tool_name)
        failure = _envelope("failed", str(exc), is_error=True)
        record = await store.get_tool_call(runtime_run_id, tool_call_id)
        if record and record.get("state") not in TOOL_TERMINAL:
            await store.update_tool_call(
                runtime_run_id,
                tool_call_id,
                state="failed",
                result=failure,
            )
        if not future.done():
            future.set_result(failure)
        return failure
    else:
        if not future.done():
            future.set_result(result)
        return result


async def _execute_leader(
    request: Request,
    *,
    ctx: Any,
    run: Any,
    runtime_run_id: str,
    tool_call_id: str,
    run_id: str,
    session_id: str,
    project_id: str | None,
    tool_name: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    store: RuntimeRunStore = request.app.state.runtime_run_store
    tracker = get_run_tracker()
    emitter = AgentEventEmitter(session_id, run_id)

    # Distinct calls serialize per run. The status/cancellation recheck after
    # acquiring this lock closes the queued-after-stop race.
    async with ctx.execution_lock:
        if (
            ctx.cancel_event.is_set()
            or run.status not in {"running", "waiting_approval"}
        ):
            failure = _envelope(
                "failed",
                f"Run stopped before tool execution (status={run.status})",
                is_error=True,
            )
            await store.update_tool_call(
                runtime_run_id,
                tool_call_id,
                state="failed",
                result=failure,
            )
            return failure

        with _request_context(
            thread_id=session_id,
            emitter=emitter,
            bundle=ctx.bundle,
        ):
            state: dict[str, Any] = {
                "run_id": run_id,
                "session_id": session_id,
                "project_id": project_id,
                "messages": [],
                "tools": [],
                "tool_callables": {},
                "pending_tool_calls": [
                    {
                        "tool_name": tool_name,
                        "tool_input": dict(params),
                        "call_id": tool_call_id,
                    }
                ],
                "guardrail_verdicts": [],
            }
            definitions, callables = (
                await ctx.bundle.tool_availability.resolve_tools(state)
            )
            state["tools"] = definitions
            state["tool_callables"] = callables
            if tool_name not in callables:
                availability = ctx.bundle.tool_availability
                exists = bool(
                    getattr(availability, "has_tool", lambda _name: False)(
                        tool_name
                    )
                )
                raise HTTPException(
                    403 if exists else 404,
                    (
                        f"Tool {tool_name!r} is disabled for this session"
                        if exists
                        else f"Unknown tool: {tool_name}"
                    ),
                )

            state = await ctx.bundle.hooks.run("preToolCallHook", state)
            matched = next(
                (
                    call
                    for call in state.get("pending_tool_calls", [])
                    if call.get("call_id") == tool_call_id
                ),
                None,
            )
            verdict = next(
                (
                    item
                    for item in state.get("guardrail_verdicts", [])
                    if item.get("tool_call_id") == tool_call_id
                    and item.get("phase") == "pre"
                ),
                None,
            )

            if matched is None and verdict and verdict.get("mode") == "user_approval":
                approval = await _await_approval(
                    ctx=ctx,
                    run=run,
                    store=store,
                    tracker=tracker,
                    emitter=emitter,
                    runtime_run_id=runtime_run_id,
                    tool_call_id=tool_call_id,
                    run_id=run_id,
                    verdict=verdict,
                    tool_name=tool_name,
                    tool_input=dict(params),
                )
                if approval["status"] != "approved":
                    if approval["status"] == "cancelled":
                        return _envelope(
                            "failed",
                            "Run cancelled while awaiting approval",
                            is_error=True,
                            guardrail_id=verdict.get("guardrail_id"),
                        )
                    denied = _envelope(
                        "denied",
                        {
                            "denied": True,
                            "message": approval.get("feedback")
                            or "The user denied this action. Do not retry it.",
                            "feedback": approval.get("feedback"),
                        },
                        is_error=True,
                        guardrail_id=verdict.get("guardrail_id"),
                    )
                    record = await store.get_tool_call(
                        runtime_run_id, tool_call_id
                    )
                    if record and record.get("state") not in TOOL_TERMINAL:
                        await store.update_tool_call(
                            runtime_run_id,
                            tool_call_id,
                            state="denied",
                            result=denied,
                        )
                    return denied
                clean_params = dict(params)
            elif matched is None:
                message = (
                    verdict.get("message")
                    if isinstance(verdict, dict)
                    else "Tool call blocked by policy hook"
                )
                denied = _envelope(
                    "denied",
                    {"blocked": message},
                    is_error=True,
                    guardrail_id=(
                        verdict.get("guardrail_id")
                        if isinstance(verdict, dict)
                        else None
                    ),
                )
                await store.update_tool_call(
                    runtime_run_id,
                    tool_call_id,
                    state="denied",
                    result=denied,
                )
                return denied
            else:
                clean_params = dict(matched.get("tool_input") or params)

            # Cancellation may win an approval race; never resume after stop.
            if (
                ctx.cancel_event.is_set()
                or run.status not in {"running", "waiting_approval"}
            ):
                failure = _envelope(
                    "failed",
                    "Run was cancelled before approved tool execution",
                    is_error=True,
                )
                record = await store.get_tool_call(
                    runtime_run_id, tool_call_id
                )
                if record and record.get("state") not in TOOL_TERMINAL:
                    await store.update_tool_call(
                        runtime_run_id,
                        tool_call_id,
                        state="failed",
                        result=failure,
                    )
                return failure

            await store.update_tool_call(
                runtime_run_id, tool_call_id, state="executing"
            )
            tracker.start_tool(session_id, tool_call_id, tool_name)
            tracker.append_event(
                session_id,
                emitter.tool_call_start(tool_call_id, tool_name),
            )
            tracker.append_event(
                session_id,
                emitter.tool_call_args(
                    tool_call_id,
                    json.dumps(clean_params, default=str),
                ),
            )
            tracker.append_event(
                session_id, emitter.tool_call_end(tool_call_id)
            )

            started = asyncio.get_running_loop().time()
            started_at = datetime.now(timezone.utc).isoformat()

            def report_progress(progress: dict[str, Any]) -> None:
                payload = {
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                    "startedAt": started_at,
                    "elapsedMs": round(
                        (
                            asyncio.get_running_loop().time()
                            - started
                        )
                        * 1000
                    ),
                    "emittedAt": datetime.now(timezone.utc).isoformat(),
                    **progress,
                }
                tracker.update_tool_progress(
                    session_id, tool_call_id, payload
                )
                tracker.append_event(
                    session_id, emitter.custom("tool:progress", payload)
                )

            try:
                report_progress(
                    {
                        "phase": "starting",
                        "label": f"Starting {tool_name}",
                    }
                )
                with tool_progress_context(report_progress):
                    result = await callables[tool_name](**clean_params)
                is_error = False
            except Exception as exc:
                logger.exception("Hermes Dataclaw tool failed: %s", tool_name)
                result = {"error": str(exc)}
                is_error = True
            finally:
                tracker.finish_tool(session_id, tool_call_id)

            result_json = json.dumps(result, default=str)
            tracker.append_event(
                session_id,
                emitter.tool_call_result(tool_call_id, result_json),
            )
            post_state = {
                **state,
                "pending_tool_calls": [],
                "tool_results": [
                    {
                        "call_id": tool_call_id,
                        "tool_name": tool_name,
                        "tool_input": clean_params,
                        "result": result_json,
                        "is_error": is_error,
                    }
                ],
            }
            await ctx.bundle.hooks.run("postToolCallHook", post_state)

            message: dict[str, Any] = {
                "role": "tool_call",
                "messageId": f"tc-{tool_call_id}",
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "args": json.dumps(clean_params, default=str),
                "result": result_json,
                "status": "error" if is_error else "complete",
                "startedAt": started_at,
                "finishedAt": datetime.now(timezone.utc).isoformat(),
            }
            redacted = json.dumps(redact_for_llm(result), default=str)
            if redacted != result_json:
                message["result_for_llm"] = redacted
            await sessions.append_message(session_id, message)

            terminal_state = "failed" if is_error else "completed"
            envelope = _envelope(
                terminal_state, result, is_error=is_error
            )
            await store.update_tool_call(
                runtime_run_id,
                tool_call_id,
                state=terminal_state,
                result=envelope,
            )
            return envelope


async def _await_approval(
    *,
    ctx: Any,
    run: Any,
    store: RuntimeRunStore,
    tracker: Any,
    emitter: AgentEventEmitter,
    runtime_run_id: str,
    tool_call_id: str,
    run_id: str,
    verdict: dict[str, Any],
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    approval_id = f"guardrail-{uuid.uuid4()}"
    approval_event = asyncio.Event()
    run.guardrail_approvals[approval_id] = approval_event
    action = await register_guardrail_action(
        run,
        approval_id=approval_id,
        guardrail_id=verdict.get("guardrail_id"),
        tool_call_id=tool_call_id,
        message=verdict.get("message", "Approval required"),
        severity=verdict.get("severity", "warning"),
        timeout_seconds=APPROVAL_WAIT_SECONDS,
        tool_name=tool_name,
        tool_input=tool_input,
    )
    await store.update_tool_call(
        runtime_run_id,
        tool_call_id,
        state="waiting_approval",
        approvalId=approval_id,
    )
    if not tracker.transition_run(run.thread_id, "waiting_approval"):
        await store.update_tool_call(
            runtime_run_id,
            tool_call_id,
            state="failed",
            result=_envelope(
                "failed",
                f"Run cannot await approval (status={run.status})",
                is_error=True,
            ),
        )
        await resolve_guardrail_action(
            run,
            approval_id,
            state="cancelled",
            approved=False,
            feedback=f"Run cannot await approval (status={run.status})",
        )
        run.guardrail_approvals.pop(approval_id, None)
        return {"status": "cancelled", "feedback": None}
    try:
        await store.update_run(run_id, status="waiting_approval")
    except Exception:
        logger.exception("Failed persisting Hermes waiting_approval")
    tracker.append_event(
        run.thread_id,
        emitter.custom(
            "guardrail:approval_required",
            {
                "approvalId": approval_id,
                "guardrailId": verdict.get("guardrail_id"),
                "toolCallId": tool_call_id,
                "message": verdict.get("message", "Approval required"),
                "severity": verdict.get("severity", "warning"),
                "createdAt": action["createdAt"],
                "expiresAt": action["expiresAt"],
                "tool": action.get("tool"),
            },
        ),
    )

    approval_task = asyncio.create_task(approval_event.wait())
    cancel_task = asyncio.create_task(ctx.cancel_event.wait())
    try:
        done, pending = await asyncio.wait(
            {approval_task, cancel_task},
            timeout=APPROVAL_WAIT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        # Cancellation wins even if approval and cancellation arrive in the
        # same event-loop turn.
        if ctx.cancel_event.is_set() or run.status in {
            "stopping",
            "cancelled",
            "failed",
            "error",
            "finished",
            "completed",
        }:
            await store.update_tool_call(
                runtime_run_id,
                tool_call_id,
                state="failed",
                result=_envelope(
                    "failed",
                    "Run cancelled while awaiting approval",
                    is_error=True,
                ),
            )
            await resolve_guardrail_action(
                run,
                approval_id,
                state="cancelled",
                approved=False,
                feedback="Run cancelled while awaiting approval.",
            )
            return {"status": "cancelled", "feedback": None}
        timed_out = False
        if approval_task not in done:
            timed_out = True
            run.guardrail_decisions[approval_id] = {
                "approved": False,
                "feedback": "Approval timed out.",
            }
        decision = run.guardrail_decisions.get(
            approval_id, {"approved": False}
        )
        if not decision.get("approved"):
            if run.status == "waiting_approval":
                tracker.transition_run(run.thread_id, "running")
                try:
                    await store.update_run(run_id, status="running")
                except Exception:
                    logger.exception(
                        "Failed persisting Hermes approval denial resume"
                    )
            tracker.append_event(
                run.thread_id,
                emitter.custom(
                    "guardrail:denied",
                    {
                        "approvalId": approval_id,
                        "toolCallId": tool_call_id,
                        "state": "timed_out" if timed_out else "denied",
                        "feedback": decision.get("feedback"),
                    },
                ),
            )
            await resolve_guardrail_action(
                run,
                approval_id,
                state="timed_out" if timed_out else "denied",
                approved=False,
                feedback=decision.get("feedback"),
            )
            return {
                "status": "denied",
                "feedback": decision.get("feedback"),
            }

        # Restore running only if this approval still owns the waiting state.
        if run.status != "waiting_approval":
            await store.update_tool_call(
                runtime_run_id,
                tool_call_id,
                state="failed",
                result=_envelope(
                    "failed",
                    "Run stopped before the approved action could resume",
                    is_error=True,
                ),
            )
            await resolve_guardrail_action(
                run,
                approval_id,
                state="cancelled",
                approved=False,
                feedback="Run stopped before the approved action could resume.",
            )
            return {"status": "cancelled", "feedback": None}
        await store.update_tool_call(
            runtime_run_id, tool_call_id, state="approved"
        )
        tracker.transition_run(run.thread_id, "running")
        try:
            await store.update_run(run_id, status="running")
        except Exception:
            logger.exception("Failed persisting Hermes approval resume")
        tracker.append_event(
            run.thread_id,
            emitter.custom(
                "guardrail:approved",
                {
                    "approvalId": approval_id,
                    "toolCallId": tool_call_id,
                },
            ),
        )
        await resolve_guardrail_action(
            run,
            approval_id,
            state="approved",
            approved=True,
            feedback=decision.get("feedback"),
        )
        return {"status": "approved", "feedback": decision.get("feedback")}
    except asyncio.CancelledError:
        await resolve_guardrail_action(
            run,
            approval_id,
            state="cancelled",
            approved=False,
            feedback="Run cancelled while awaiting approval.",
        )
        raise
    finally:
        approval_task.cancel()
        cancel_task.cancel()
        run.guardrail_approvals.pop(approval_id, None)
        run.guardrail_decisions.pop(approval_id, None)
