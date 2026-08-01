"""Hermes Runs API AgentProvider."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from dataclaw.api.run_tracker import get_run_tracker
from dataclaw.events.emitter import AgentEventEmitter
from dataclaw.providers.config_field import ConfigField
from dataclaw.providers.llm.provider import (
    BrokerEvent,
    TextDeltaEvent,
    TurnCompleteEvent,
)
from dataclaw.schema import Message
from dataclaw.storage.runtime_runs import (
    RUN_TERMINAL,
    InvalidTransition,
    RuntimeRunStore,
)
from dataclaw_hermes.client import HermesAPIError, HermesClient
from dataclaw_hermes.config import HermesConfig
from dataclaw_hermes.events import event_name, text_delta
from dataclaw_hermes.identity import encode_correlation

logger = logging.getLogger(__name__)


def _message_content(message: Message) -> str:
    if isinstance(message.content, str):
        return message.content
    return message.text()


def _wire_messages(messages: list[Message]) -> list[dict[str, str]]:
    """Hermes Runs currently accepts role/content history, not tool blocks."""
    result: list[dict[str, str]] = []
    for message in messages:
        role = message.role
        if role == "tool_call":
            # Preserve who initiated a historical tool interaction even though
            # Hermes' Runs history accepts only role/content messages.
            role = "assistant"
        elif role == "tool_result":
            role = "user"
        elif role not in {"system", "user", "assistant"}:
            role = "user"
        result.append({"role": role, "content": _message_content(message)})
    return result


def _tool_catalog(tools: list[dict[str, Any]]) -> str:
    catalog = [
        {
            "name": tool.get("name"),
            "description": tool.get("description", ""),
            "parameters": tool.get("parameters") or {
                "type": "object",
                "properties": {},
            },
        }
        for tool in tools
    ]
    return (
        "\n\nDataclaw tools are available only through the `dataclaw_tool` "
        "dispatcher. Pass one exact enabled `tool_name` and its `params`. "
        "Do not call any tool absent from this catalog:\n"
        + json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    )


class HermesAgentProvider:
    def __init__(
        self,
        client: HermesClient,
        config: HermesConfig,
        store: RuntimeRunStore,
    ) -> None:
        self.client = client
        self.config = config
        self.store = store

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return []

    async def stream_turn(
        self, state: dict[str, Any]
    ) -> AsyncIterator[BrokerEvent]:
        run_id = state.get("run_id")
        try:
            async for event in self._stream_turn_impl(state):
                yield event
        except asyncio.CancelledError:
            if isinstance(run_id, str) and run_id:
                await self._record_terminal(run_id, "cancelled")
            raise
        except Exception:
            if isinstance(run_id, str) and run_id:
                # A stream loss is explicitly recorded as unknown below.
                # Preserve that outcome instead of pretending the final
                # response was observed.
                await self._record_terminal(
                    run_id, "failed", preserve_unknown=True
                )
            raise

    async def _record_terminal(
        self,
        run_id: str,
        status: str,
        *,
        preserve_unknown: bool = False,
    ) -> None:
        try:
            record = await self.store.get_run(run_id)
            if record is None or record.get("status") in RUN_TERMINAL:
                return
            if preserve_unknown and record.get("status") == "unknown":
                return
            await self.store.update_run(run_id, status=status)
        except (InvalidTransition, KeyError):
            return
        except Exception:
            logger.exception(
                "Failed to persist Hermes terminal status for %s", run_id
            )

    async def _stream_turn_impl(
        self, state: dict[str, Any]
    ) -> AsyncIterator[BrokerEvent]:
        run_id = state.get("run_id")
        session_id = state.get("session_id")
        project_id = state.get("project_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("Hermes requires AgentState.run_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Hermes requires AgentState.session_id")
        if project_id is not None and not isinstance(project_id, str):
            raise ValueError("Hermes project_id must be a string or null")

        messages = list(state.get("messages") or [])
        if not messages:
            raise ValueError("Hermes requires at least one input message")
        wire_messages = _wire_messages(messages)
        correlation_id = encode_correlation(
            run_id=run_id,
            session_id=session_id,
            project_id=project_id,
        )
        await self.store.create_run(
            run_id=run_id,
            session_id=session_id,
            project_id=project_id,
        )
        await self.store.update_run(
            run_id,
            status="running",
            runtimeSessionId=correlation_id,
        )

        instruction_parts = [
            str(state.get("system_prompt") or "").strip(),
            str(state.get("system_prompt_dynamic") or "").strip(),
            "\n".join(state.get("skill_prompt_fragments") or []).strip(),
        ]
        instructions = "\n\n".join(
            part for part in instruction_parts if part
        ) + _tool_catalog(list(state.get("tools") or []))
        payload: dict[str, Any] = {
            "input": wire_messages,
            "session_id": correlation_id,
            "instructions": instructions,
        }
        if self.config.model:
            payload["model"] = self.config.model

        accepted = await self.client.create_run(payload)
        runtime_run_id = accepted["run_id"]
        await self.store.update_run(run_id, runtimeRunId=runtime_run_id)

        tracker = get_run_tracker()
        tracker.set_runtime_metadata(
            session_id,
            runtime="hermes",
            runtime_run_id=runtime_run_id,
            runtime_session_id=correlation_id,
        )
        emitter = AgentEventEmitter(session_id, run_id)
        saw_text = False
        terminal = False

        async for event in self.client.stream_run_events(runtime_run_id):
            if event.get("run_id") not in {None, runtime_run_id}:
                raise HermesAPIError("Hermes event run_id mismatch")
            name = event_name(event)
            delta = text_delta(event)
            if delta:
                saw_text = True
                yield TextDeltaEvent(delta)
                continue
            if name in {"tool.started", "tool.completed"}:
                tracker.append_event(
                    session_id,
                    emitter.custom(
                        f"hermes:{name.replace('.', '_')}",
                        {
                            "runtimeRunId": runtime_run_id,
                            "tool": event.get("tool"),
                            "duration": event.get("duration"),
                            "error": event.get("error"),
                        },
                    ),
                )
            elif name == "reasoning.available":
                tracker.append_event(
                    session_id,
                    emitter.custom(
                        "hermes:progress",
                        {"text": event.get("text", "")},
                    ),
                )
            elif name == "run.completed":
                terminal = True
                output = str(event.get("output") or "")
                if output and not saw_text:
                    yield TextDeltaEvent(output)
                usage = event.get("usage")
                if isinstance(usage, dict):
                    tracker.set_runtime_metadata(session_id, usage=usage)
                    tracker.append_event(
                        session_id,
                        emitter.custom("hermes:usage", usage),
                    )
                try:
                    await self.store.update_run(
                        run_id, status="completed"
                    )
                except InvalidTransition:
                    pass
                state.setdefault("metadata", {})["agent_text"] = output
                yield TurnCompleteEvent(
                    has_pending_tool_calls=False, skip_persist=False
                )
                return
            elif name == "run.failed":
                terminal = True
                message = str(event.get("error") or "Hermes run failed")
                try:
                    await self.store.update_run(run_id, status="failed")
                except InvalidTransition:
                    pass
                raise HermesAPIError(message)
            elif name == "run.cancelled":
                terminal = True
                try:
                    await self.store.update_run(run_id, status="cancelled")
                except InvalidTransition:
                    pass
                raise asyncio.CancelledError

        if not terminal:
            try:
                status = await self.client.status(runtime_run_id)
                outcome = str(status.get("status") or "unknown")
            except Exception:
                outcome = "unknown"
            try:
                await self.store.update_run(
                    run_id,
                    status=(
                        outcome
                        if outcome in {"failed", "cancelled"}
                        else "unknown"
                    ),
                )
            except InvalidTransition:
                pass
            raise HermesAPIError(
                f"Hermes stream ended before completion (status={outcome})"
            )

    async def aclose(self) -> None:
        await self.client.aclose()
