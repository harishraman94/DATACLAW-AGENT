"""Skills router — CRUD for skill files."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dataclaw.storage.skill_library import (
    read_library_skill,
    skill_freshness_for_installed_skill,
)
from dataclaw.storage.skills import delete_skill, list_skill_files, read_skill, write_skill

router = APIRouter()


class SkillRequest(BaseModel):
    name: str = ""
    description: str = ""
    tags: list[str] = []
    body: str = ""


@router.get("")
async def list_skills() -> list[dict[str, Any]]:
    skills = list_skill_files()
    for skill in skills:
        skill_id = str(skill.get("id") or "")
        installed = read_skill(skill_id)
        if installed is None:
            skill["installed_stale"] = False
            continue
        freshness = skill_freshness_for_installed_skill(
            skill_id,
            str(installed.get("body") or ""),
            installed,
        )
        skill.update(freshness)
        skill["installed_stale"] = bool(freshness.get("installed_stale"))
    return skills


@router.get("/{skill_id}")
async def get_skill(skill_id: str) -> dict[str, Any]:
    skill = read_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


@router.post("/{skill_id}")
async def create_skill(skill_id: str, req: SkillRequest) -> dict[str, Any]:
    if read_skill(skill_id) is not None:
        raise HTTPException(status_code=409, detail="A skill with this ID already exists.")
    if read_library_skill(skill_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="This ID is reserved by a library skill. Choose a different name for the custom skill.",
        )
    meta = {"name": req.name or skill_id, "description": req.description, "tags": req.tags}
    path = write_skill(skill_id, meta, req.body)
    return {"id": skill_id, "path": str(path), "status": "created"}


@router.put("/{skill_id}")
async def update_skill(skill_id: str, req: SkillRequest) -> dict[str, Any]:
    existing = read_skill(skill_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    if (
        existing.get("source") == "library"
        or existing.get("library_id")
        or read_library_skill(skill_id) is not None
    ):
        raise HTTPException(
            status_code=403,
            detail="Library skills are read-only. Duplicate this skill as a custom skill to edit it.",
        )
    meta = {"name": req.name or skill_id, "description": req.description, "tags": req.tags}
    path = write_skill(skill_id, meta, req.body)
    return {"id": skill_id, "path": str(path), "status": "updated"}


@router.delete("/{skill_id}")
async def remove_skill(skill_id: str) -> dict[str, str]:
    if not delete_skill(skill_id):
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"status": "deleted"}
