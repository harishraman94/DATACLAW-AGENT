"""Best-effort JSON correlation storage for external runtime runs."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dataclaw.config.paths import runtime_runs_dir

RUN_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "failed", "cancelled"},
    "running": {
        "waiting_approval",
        "stopping",
        "completed",
        "failed",
        "cancelled",
        "unknown",
    },
    "waiting_approval": {
        "running",
        "stopping",
        "failed",
        "cancelled",
        "unknown",
    },
    "stopping": {"completed", "cancelled", "failed", "unknown"},
    "unknown": {"completed", "failed", "cancelled"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}
TOOL_TRANSITIONS: dict[str, set[str]] = {
    "received": {
        "executing",
        "waiting_approval",
        "denied",
        "failed",
        "unknown",
    },
    "waiting_approval": {"approved", "denied", "failed", "unknown"},
    "approved": {"executing", "failed", "unknown"},
    "executing": {"completed", "failed", "unknown"},
    "completed": set(),
    "denied": set(),
    "failed": set(),
    "unknown": set(),
}
RUN_TERMINAL = frozenset({"completed", "failed", "cancelled"})
TOOL_TERMINAL = frozenset({"completed", "denied", "failed", "unknown"})


class InvalidTransition(ValueError):
    pass


class RevisionConflict(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_arguments_digest(arguments: dict[str, Any]) -> str:
    raw = json.dumps(
        arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RuntimeRunStore:
    """One-file-per-record store with in-process revision checks."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or runtime_runs_dir()
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        return self._locks.setdefault(key, asyncio.Lock())

    def _run_path(self, run_id: str) -> Path:
        return self.root / "runs" / f"{run_id}.json"

    def _tool_path(self, runtime_run_id: str, call_id: str) -> Path:
        digest = hashlib.sha256(
            f"{runtime_run_id}\0{call_id}".encode("utf-8")
        ).hexdigest()
        return self.root / "tool-calls" / f"{digest}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text())

    @staticmethod
    def _write(path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, default=str))

    async def create_run(
        self,
        *,
        run_id: str,
        session_id: str,
        project_id: str | None,
        runtime: str = "hermes",
    ) -> dict[str, Any]:
        path = self._run_path(run_id)
        async with self._lock(f"run:{run_id}"):
            existing = self._read(path)
            if existing is not None:
                return existing
            now = _now()
            record = {
                "runId": run_id,
                "runtime": runtime,
                "workKind": "chat",
                "sessionId": session_id,
                "projectId": project_id,
                "runtimeSessionId": None,
                "runtimeRunId": None,
                "runtimeTaskId": None,
                "status": "queued",
                "revision": 0,
                "createdAt": now,
                "updatedAt": now,
            }
            self._write(path, record)
            return record

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        async with self._lock(f"run:{run_id}"):
            return self._read(self._run_path(run_id))

    async def update_run(
        self,
        run_id: str,
        *,
        expected_revision: int | None = None,
        status: str | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        path = self._run_path(run_id)
        async with self._lock(f"run:{run_id}"):
            record = self._read(path)
            if record is None:
                raise KeyError(run_id)
            if (
                expected_revision is not None
                and record["revision"] != expected_revision
            ):
                raise RevisionConflict(run_id)
            if status is not None and status != record["status"]:
                allowed = RUN_TRANSITIONS.get(record["status"], set())
                if status not in allowed:
                    raise InvalidTransition(
                        f"run {record['status']} -> {status}"
                    )
                record["status"] = status
            record.update(fields)
            record["revision"] += 1
            record["updatedAt"] = _now()
            self._write(path, record)
            return record

    async def create_tool_call(
        self,
        *,
        runtime_run_id: str,
        tool_call_id: str,
        dataclaw_run_id: str,
        session_id: str,
        project_id: str | None,
        tool_name: str,
        arguments_digest: str,
    ) -> dict[str, Any]:
        path = self._tool_path(runtime_run_id, tool_call_id)
        key = f"tool:{runtime_run_id}:{tool_call_id}"
        async with self._lock(key):
            existing = self._read(path)
            if existing is not None:
                return existing
            record = {
                "runtimeRunId": runtime_run_id,
                "toolCallId": tool_call_id,
                "dataclawRunId": dataclaw_run_id,
                "sessionId": session_id,
                "projectId": project_id,
                "toolName": tool_name,
                "argumentsDigest": arguments_digest,
                "state": "received",
                "approvalId": None,
                "result": None,
                "revision": 0,
                "createdAt": _now(),
                "updatedAt": _now(),
            }
            self._write(path, record)
            return record

    async def get_tool_call(
        self, runtime_run_id: str, tool_call_id: str
    ) -> dict[str, Any] | None:
        key = f"tool:{runtime_run_id}:{tool_call_id}"
        async with self._lock(key):
            return self._read(self._tool_path(runtime_run_id, tool_call_id))

    async def update_tool_call(
        self,
        runtime_run_id: str,
        tool_call_id: str,
        *,
        expected_revision: int | None = None,
        state: str | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        path = self._tool_path(runtime_run_id, tool_call_id)
        key = f"tool:{runtime_run_id}:{tool_call_id}"
        async with self._lock(key):
            record = self._read(path)
            if record is None:
                raise KeyError((runtime_run_id, tool_call_id))
            if (
                expected_revision is not None
                and record["revision"] != expected_revision
            ):
                raise RevisionConflict(key)
            if state is not None and state != record["state"]:
                allowed = TOOL_TRANSITIONS.get(record["state"], set())
                if state not in allowed:
                    raise InvalidTransition(
                        f"tool {record['state']} -> {state}"
                    )
                record["state"] = state
            record.update(fields)
            record["revision"] += 1
            record["updatedAt"] = _now()
            self._write(path, record)
            return record

    async def fail_nonterminal_records(self) -> dict[str, int]:
        """Terminalize process-lifetime work after a restart.

        Runs fail because the owning chat task is gone. Tool calls become
        unknown because their side effect may have happened before the
        process stopped and therefore must never be guessed/retried.
        """
        runs_path = self.root / "runs"
        run_count = 0
        if runs_path.exists():
            for path in runs_path.glob("*.json"):
                try:
                    record = json.loads(path.read_text())
                    if record.get("status") in RUN_TERMINAL:
                        continue
                    record["status"] = "failed"
                    record["revision"] = int(record.get("revision", 0)) + 1
                    record["updatedAt"] = _now()
                    record["restartReason"] = "Dataclaw restarted"
                    self._write(path, record)
                    run_count += 1
                except (OSError, ValueError, TypeError):
                    continue

        tool_count = 0
        tools_path = self.root / "tool-calls"
        if tools_path.exists():
            for path in tools_path.glob("*.json"):
                try:
                    record = json.loads(path.read_text())
                    if record.get("state") in TOOL_TERMINAL:
                        continue
                    result = {
                        "state": "unknown",
                        "isError": True,
                        "content": (
                            "Dataclaw restarted before the tool outcome was "
                            "durably confirmed; the call will not be retried"
                        ),
                        "guardrailId": None,
                    }
                    record["state"] = "unknown"
                    record["result"] = result
                    record["revision"] = int(record.get("revision", 0)) + 1
                    record["updatedAt"] = _now()
                    self._write(path, record)
                    tool_count += 1
                except (OSError, ValueError, TypeError):
                    continue
        return {"runs": run_count, "tool_calls": tool_count}

    async def fail_nonterminal_runs(self) -> int:
        """Backward-compatible run-only count used by startup callers."""
        return (await self.fail_nonterminal_records())["runs"]
