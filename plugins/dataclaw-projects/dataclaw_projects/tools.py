"""Project and subagent tools for the agent."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

from dataclaw_projects.subagents import get_subagent_definition, list_subagent_definitions

logger = logging.getLogger(__name__)


# Module-level subagent allowlist filter — set by a preToolCallHook before
# each agent turn (mirrors the dataset filter in dataclaw_data). None means
# "all subagents allowed"; a list (possibly empty) means "only these ids".
_allowed_subagent_ids: ContextVar[tuple[str, ...] | None] = ContextVar(
    "dataclaw_allowed_subagent_ids",
    default=None,
)


def set_allowed_subagent_ids(ids: list[str] | None) -> None:
    """Set the per-session subagent allowlist for the current request."""
    _allowed_subagent_ids.set(tuple(ids) if ids is not None else None)


def _filter_subagents(defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    allowed_ids = _allowed_subagent_ids.get()
    if allowed_ids is None:
        return defs
    allowed = set(allowed_ids)
    return [d for d in defs if d.get("id") in allowed]


def _check_subagent_allowed(subagent_id: str) -> None:
    """Raise if the subagent isn't in the current session's allowlist."""
    allowed_ids = _allowed_subagent_ids.get()
    if allowed_ids is not None and subagent_id not in set(allowed_ids):
        raise ValueError(f"Subagent '{subagent_id}' is not enabled for this session")


async def list_subagents_tool(**kw: Any) -> dict[str, Any]:
    """List subagent definitions enabled for the current chat session."""
    return {"subagents": _filter_subagents(list_subagent_definitions())}


def make_delegate_to_subagent(
    providers: Any,
    tool_registry: Any,
):
    """Create a delegate_to_subagent closure with access to providers and tool registry."""

    async def delegate_to_subagent(
        *,
        subagent_name: str,
        task: str,
        conversation_id: str = "",
        **kw: Any,
    ) -> dict[str, Any]:
        """Delegate a task to a named subagent."""
        from dataclaw.hooks.base import HookError
        from dataclaw.providers.sub_agent.provider import (
            DelegateEvent,
            SubAgentContext,
        )

        # Reject delegations to subagents not enabled for this chat session.
        # Mirrors `_check_dataset_allowed` in dataclaw_data — the agent can
        # see the subagent definition exists, but the session-level filter
        # blocks it from being run.
        try:
            _check_subagent_allowed(subagent_name)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        # Look up the subagent definition
        try:
            definition = get_subagent_definition(subagent_name)
        except KeyError:
            return {
                "status": "error",
                "message": f"Subagent not found: {subagent_name}",
            }

        agent_type = definition.get("agent_type", "llm")
        registry = providers.sub_agent_registry
        sub_agent = registry.get(agent_type)
        if sub_agent is None:
            available = [t["agent_type"] for t in registry.list_types()]
            return {
                "status": "error",
                "message": f"No provider for agent_type={agent_type!r}. Available: {available}",
            }

        # Resolve the same effective session/project tool scope as the parent,
        # then narrow it further to the subagent definition's allowlist.
        allowed = set(definition.get("allowed_tools", []))
        session_id = str(
            kw.get("dataclaw_session_id")
            or kw.get("session_id")
            or ""
        )
        project_id = ""
        if session_id:
            try:
                from dataclaw.storage.sessions import get_session

                session = await get_session(session_id)
                project_id = str((session or {}).get("projectId") or "")
            except Exception:
                pass
        resolved_tools, resolved_callables = await tool_registry.resolve_tools({
            "session_id": session_id,
            "project_id": project_id,
            "messages": [],
        })
        tools = [
            tool
            for tool in resolved_tools
            if tool.get("name") != "delegate_to_subagent"
            and (not allowed or tool.get("name") in allowed)
        ]
        tool_callables = {
            name: fn
            for name, fn in resolved_callables.items()
            if name != "delegate_to_subagent" and (not allowed or name in allowed)
        }

        # Build emit callback for UI progress
        emit = _build_emit_callback()

        # Load prior conversation if resuming
        prior_messages: list[dict[str, Any]] = []
        if conversation_id:
            conv = await _load_conversation(conversation_id)
            if conv:
                prior_messages = conv.get("messages", [])

        # Build config, injecting project directory if available
        sa_config = dict(definition.get("config", {}))
        if not sa_config.get("cwd"):
            project_dir = _resolve_project_dir()
            if project_dir:
                sa_config["cwd"] = project_dir

        # Build context
        context = SubAgentContext(
            definition=definition,
            tools=tools,
            tool_callables=tool_callables,
            config=sa_config,
            emit=emit,
            sub_agent_hooks=providers.sub_agent_hooks,
            prior_messages=prior_messages,
            conversation_id=conversation_id,
        )

        # Run pre-delegate hooks
        hooks = providers.sub_agent_hooks
        delegate_event = DelegateEvent(
            subagent_name=subagent_name,
            agent_type=agent_type,
            task=task,
            context=context,
        )
        try:
            delegate_event = await hooks.run_delegate(delegate_event)
        except HookError as e:
            return {
                "status": "error",
                "message": f"Delegation blocked by hook: {e}",
            }

        # Execute
        try:
            result = await sub_agent.run(
                delegate_event.task,
                context=delegate_event.context,
            )
        except Exception as e:
            logger.exception("Subagent execution failed: %s", e)
            return {
                "status": "error",
                "message": f"Subagent execution failed: {e}",
            }

        # Run post-delegate hooks
        delegate_event.result = result
        try:
            delegate_event = await hooks.run_delegate_response(delegate_event)
        except HookError as e:
            logger.warning("Post-delegate hook error: %s", e)

        # Persist conversation for future follow-ups
        final_result = delegate_event.result
        if final_result.conversation_id:
            await _save_conversation(
                final_result.conversation_id,
                subagent_name=subagent_name,
                messages=final_result.metadata.get("messages", []),
            )

        return final_result.to_dict()

    return delegate_to_subagent


def _build_emit_callback():
    """Build an emit callback using context vars. Returns None if not in an agent loop."""
    try:
        from dataclaw.api.context import current_emitter, current_thread_id
        from dataclaw.api.run_tracker import get_run_tracker

        thread_id = current_thread_id.get()
        current_emitter.get()
        tracker = get_run_tracker()

        def emit(event_str: str) -> None:
            tracker.append_event(thread_id, event_str)

        return emit
    except LookupError:
        return None


def _resolve_project_dir() -> str | None:
    """Resolve the active project's working directory.

    The workspace plugin sets the project directory via a preToolCallHook
    when a project is active. We read it here to inject into subagent config.
    """
    try:
        from dataclaw_workspace.tools import get_project_dir

        project_dir = get_project_dir()
        if project_dir is not None:
            return str(project_dir)
    except ImportError:
        pass
    return None


async def _load_conversation(conversation_id: str) -> dict[str, Any] | None:
    """Load a subagent conversation from the current session."""
    try:
        from dataclaw.api.context import current_thread_id
        from dataclaw.storage import sessions

        thread_id = current_thread_id.get()
        return await sessions.get_subagent_conversation(thread_id, conversation_id)
    except LookupError:
        return None


async def _save_conversation(
    conversation_id: str,
    *,
    subagent_name: str,
    messages: list[dict[str, Any]],
) -> None:
    """Persist a subagent conversation to the current session."""
    try:
        from dataclaw.api.context import current_thread_id
        from dataclaw.storage import sessions

        thread_id = current_thread_id.get()
        await sessions.save_subagent_conversation(
            thread_id,
            conversation_id,
            subagent_name=subagent_name,
            messages=messages,
        )
    except LookupError:
        pass
