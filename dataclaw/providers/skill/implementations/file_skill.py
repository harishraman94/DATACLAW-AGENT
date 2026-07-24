"""File-based skill provider.

Reads skill files from a directory (default ~/.dataclaw/skills/).
Each skill is a markdown file with YAML frontmatter:

    ---
    name: data_profiling
    description: Guides the agent through dataset profiling
    tags: [data, analysis]
    ---

    When asked to profile a dataset, follow these steps:
    1. Load the dataset
    2. Run statistical summaries
    ...
"""

from __future__ import annotations

import hashlib
import logging
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import yaml

from dataclaw.config.paths import skills_dir
from dataclaw.storage.skill_library import skill_freshness_for_installed_skill
from dataclaw.state import AgentState

logger = logging.getLogger(__name__)


def _parse_skill_file(path: Path) -> dict[str, Any] | None:
    """Parse a skill markdown file with YAML frontmatter."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        logger.warning("Invalid YAML frontmatter in %s", path)
        return None

    body = parts[2].strip()
    skill = {
        "id": path.stem,
        "name": meta.get("name", path.stem),
        "description": meta.get("description", ""),
        "tags": meta.get("tags", []),
        "body": body,
        "path": str(path),
    }
    for key, value in meta.items():
        skill.setdefault(key, value)
    freshness = skill_freshness_for_installed_skill(path.stem, body, meta)
    skill.update(freshness)
    return skill


class FileSkillProvider:
    """Reads skills from markdown files in a directory."""

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = directory or skills_dir()
        # Resolution is request-local. The provider is a process singleton,
        # while native chat runs and bridge requests may execute concurrently.
        # Instance fields here would let one session overwrite another
        # session's allowlist between resolve_skills() and fetch_skill().
        self._resolved_skills: ContextVar[tuple[dict[str, Any], ...] | None] = (
            ContextVar(f"dataclaw_resolved_skills_{id(self)}", default=None)
        )

    def _load_all(self) -> list[dict[str, Any]]:
        if not self._dir.exists():
            return []
        skills = []
        for path in sorted(self._dir.glob("*.md")):
            skill = _parse_skill_file(path)
            if skill:
                skills.append(skill)
        return skills

    async def resolve_skills(self, state: AgentState) -> list[dict[str, Any]]:
        all_skills = self._load_all()

        # Check session-level allowlist first, then project-level
        allowed_ids = self._resolve_allowed_ids(state)
        if allowed_ids is not None:
            filtered = [s for s in all_skills if s["id"] in allowed_ids]
        else:
            filtered = all_skills

        # Assign serial IDs for unambiguous LLM tool calls
        for i, skill in enumerate(filtered):
            skill["serial_id"] = f"skill_{i + 1}"

        self._resolved_skills.set(tuple(filtered))
        return filtered

    def _resolve_allowed_ids(self, state: AgentState) -> list[str] | None:
        """Resolve skill allowlist from session → project → None (all)."""
        import json
        from dataclaw.config.paths import sessions_dir

        session_id = state.get("session_id")
        project_id = state.get("project_id")
        if session_id:
            try:
                path = sessions_dir() / f"{session_id}.json"
                if not path.exists():
                    return []
                data = json.loads(path.read_text())
                if data.get("skillIds") is not None:
                    return data["skillIds"]
                project_id = project_id or data.get("projectId") or data.get("project_id")
            except Exception:
                # Fail closed: an unreadable/corrupt session grants no skills.
                # Log so this is distinguishable from a deliberately empty
                # allowlist — otherwise a transient read error looks identical
                # to "this session has no skills" and reads as broken isolation.
                logger.warning(
                    "Skill scope resolution failed for session %s; denying all skills",
                    session_id,
                    exc_info=True,
                )
                return []

        if project_id:
            try:
                from dataclaw_projects.registry import get_project
                proj = get_project(project_id)
                if proj.get("skill_ids") is not None:
                    return proj["skill_ids"]
            except Exception:
                # Fail closed on an unreadable project record, and log so the
                # denial is not silently mistaken for an empty project default.
                logger.warning(
                    "Skill scope resolution failed for project %s; denying all skills",
                    project_id,
                    exc_info=True,
                )
                return []

        return None

    async def format_for_prompt(self, skills: list[dict[str, Any]]) -> list[str]:
        """Format skill summaries for the system prompt.

        Only includes id, name, and description — not the full body.
        The agent uses the ``fetch_skill`` tool to load the full content
        when it decides to apply a skill.
        """
        if not skills:
            return []
        lines = ["Available skills (use the `fetch_skill` tool with the id to load full instructions):"]
        for skill in skills:
            sid = skill.get("serial_id", skill["id"])
            desc = skill.get("description", "")
            line = f"- {skill['name']} (id: {sid})"
            if desc:
                line += f" - {desc}"
            if skill.get("installed_stale"):
                line += " [stale installed library copy]"
            lines.append(line)
        stale_names = [str(skill.get("name") or skill.get("id")) for skill in skills if skill.get("installed_stale")]
        if stale_names:
            lines.append("")
            lines.append(
                "Skill freshness warning: installed library skills are stale versus the bundled skill-library "
                f"({', '.join(stale_names)}). Reinstall or force-update them before relying on report composition guidance."
            )
        return ["\n".join(lines)]

    async def fetch_skill(self, skill_id: str, **kwargs: Any) -> dict[str, Any]:
        """Fetch the full content of a skill by its serial ID. Used as an agent tool."""
        resolved_skills = self._resolved_skills.get()
        # Look up from the request-local resolved list first (has serial_ids).
        for skill in resolved_skills or ():
            if skill.get("serial_id") == skill_id or skill["id"] == skill_id:
                return _skill_fetch_result(skill)
        # Fallback only when no per-request resolve happened (e.g., a
        # standalone CLI invocation). If the session-aware preToolCallHook
        # ran and the requested id wasn't in the resolved set, the filter
        # excluded it on purpose — don't reach into _load_all() and bypass.
        if resolved_skills is None:
            for skill in self._load_all():
                if skill["id"] == skill_id:
                    return _skill_fetch_result(skill)
        # Bundled library entries are discoverable/installable content, not an
        # implicit execution source. A skill must be installed and inside the
        # active request scope before an agent can fetch its instructions.
        return {"content": f"Skill not found: {skill_id}", "is_error": True}

    async def list_available_skills(self, **kwargs: Any) -> dict[str, Any]:
        """List skills available for the current session. Used as an agent tool."""
        # Trust the resolved cache *only* if resolve_skills() was actually
        # called for this request (set by the preToolCallHook in app.py).
        # The old `_resolved_skills or _load_all()` fallback also fired for
        # explicit empty-list filters (a session with `skillIds: []`), so
        # filtering down to zero silently became "show everything".
        resolved_skills = self._resolved_skills.get()
        skills = list(resolved_skills) if resolved_skills is not None else self._load_all()
        lines = []
        for i, s in enumerate(skills):
            sid = s.get("serial_id", f"skill_{i + 1}")
            stale = " [stale installed library copy]" if s.get("installed_stale") else ""
            lines.append(f"- {s['name']} (id: {sid}): {s.get('description', '')}{stale}")
        return {"content": "\n".join(lines) if lines else "No skills available."}


def _skill_fetch_result(skill: dict[str, Any]) -> dict[str, Any]:
    """Return a fetch result with both the model-facing and canonical identity."""
    content = _skill_content(skill)
    return {
        "content": content,
        # Keep ``id`` as the serial id advertised to the model for protocol
        # compatibility, while exposing the stable identity for UI/auditing.
        "id": skill.get("serial_id", skill["id"]),
        "skill_id": skill["id"],
        "name": skill["name"],
        "description": skill.get("description", ""),
        "source": "installed",
        "origin": str(skill.get("source") or "local"),
        "installed": True,
        "sha256": hashlib.sha256(
            str(skill.get("body") or "").encode("utf-8")
        ).hexdigest(),
        "installed_stale": bool(skill.get("installed_stale")),
        "stale_reason": skill.get("stale_reason", ""),
    }


def _skill_content(skill: dict[str, Any]) -> str:
    warning = ""
    if skill.get("installed_stale"):
        reason = skill.get("stale_reason") or "installed copy differs from bundled skill-library"
        warning = (
            "Skill freshness warning: this installed library skill is stale versus the bundled "
            f"skill-library ({reason}). The installed copy below remains the active source; "
            "reinstall or force-update it to use the library revision.\n\n"
        )
    return f"{warning}# {skill['name']}\n\n{skill.get('body', '')}"
