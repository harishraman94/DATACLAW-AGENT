"""Session deletion cascades DataClaw-owned state without deleting projects."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from dataclaw.api.app import create_app
from dataclaw.config.paths import plugin_data_dir, sessions_dir, workspaces_dir
from dataclaw.storage import sessions
from dataclaw_analysis_review.store import append_review_run
from dataclaw_eda.store import append_hypothesis
from dataclaw_plans.store import (
    read_proposals,
    read_snapshots,
    write_proposals,
    write_snapshots,
)
from dataclaw_plans.mlflow_tools import _client, get_or_create_experiment
from dataclaw_projects.registry import create_project


@pytest.mark.asyncio
async def test_delete_session_removes_metadata_instead_of_archiving() -> None:
    session_id = "deleted-session"
    await sessions.create_session(session_id=session_id, title="Delete me")
    await sessions.upsert_capability_receipt(session_id, {
        "schemaVersion": 1,
        "runId": "run-1",
        "status": "completed",
    })

    assert await sessions.delete_session(session_id) is True
    assert await sessions.get_session(session_id) is None
    assert not (sessions_dir() / f"{session_id}.json").exists()
    assert not (sessions_dir() / ".deleted" / f"{session_id}.json").exists()


def test_delete_session_cascades_owned_workspace_and_shared_store_records() -> None:
    with TestClient(create_app()) as client:
        session_id = client.post(
            "/api/chat/sessions",
            json={"title": "Cascade me"},
        ).json()["id"]

        workspace = workspaces_dir() / session_id
        workspace.mkdir(parents=True)
        (workspace / "analysis.txt").write_text("owned")
        venv = workspaces_dir().parent / "venvs" / session_id
        venv.mkdir(parents=True)
        (venv / "marker").write_text("owned")

        append_hypothesis({"hypothesis_id": "hyp-owned"}, session_id)
        append_review_run({"review_id": "rev-owned"}, session_id)

        artifact = workspaces_dir() / "artifacts" / "art-deadbeef"
        artifact.mkdir(parents=True)
        (artifact / "meta.json").write_text(json.dumps({
            "id": "art-deadbeef",
            "session_id": session_id,
        }))
        other_artifact = workspaces_dir() / "artifacts" / "art-cafebabe"
        other_artifact.mkdir(parents=True)
        (other_artifact / "meta.json").write_text(json.dumps({
            "id": "art-cafebabe",
            "session_id": "another-session",
        }))

        write_proposals([
            {"id": "plan-owned", "session_id": session_id},
            {"id": "plan-shared", "session_id": "another-session"},
        ])
        write_snapshots([
            {
                "id": "snap-owned",
                "proposal_id": "plan-owned",
                "plan": {"id": "plan-owned", "session_id": session_id},
            },
            {
                "id": "snap-shared",
                "proposal_id": "plan-shared",
                "plan": {"id": "plan-shared", "session_id": "another-session"},
            },
        ])
        shared_dataset_marker = plugin_data_dir("data") / "shared-dataset"
        shared_dataset_marker.mkdir(parents=True)
        get_or_create_experiment(session_id)

        response = client.delete(f"/api/chat/sessions/{session_id}")

        assert response.status_code == 200, response.text
        assert response.json()["status"] == "deleted"
        assert client.get(f"/api/chat/sessions/{session_id}").status_code == 404
        assert not workspace.exists()
        assert not venv.exists()
        assert not (workspaces_dir() / "eda" / "findings" / session_id).exists()
        assert not (workspaces_dir() / "analysis-review" / session_id).exists()
        assert not artifact.exists()
        assert other_artifact.exists()
        assert [p["id"] for p in read_proposals()] == ["plan-shared"]
        assert [s["id"] for s in read_snapshots()] == ["snap-shared"]
        assert shared_dataset_marker.exists()
        assert _client().get_experiment_by_name(f"dataclaw-{session_id}") is None


def test_deleting_project_chat_keeps_project_files_and_project_venv(tmp_path) -> None:
    project_dir = tmp_path / "user-project"
    project = create_project(name="User Project", directory=str(project_dir))
    user_file = project_dir / "source.csv"
    user_file.write_text("x\n1\n")

    with TestClient(create_app()) as client:
        session_id = client.post(
            "/api/chat/sessions",
            json={"title": "Project chat", "project_id": project["id"]},
        ).json()["id"]
        session_workspace = workspaces_dir() / session_id
        session_workspace.mkdir(parents=True)
        (session_workspace / "session-output.txt").write_text("owned")
        project_venv = workspaces_dir().parent / "venvs" / project["id"]
        project_venv.mkdir(parents=True)
        (project_venv / "marker").write_text("shared")

        response = client.delete(f"/api/chat/sessions/{session_id}")

        assert response.status_code == 200, response.text
        assert not session_workspace.exists()
        assert project_dir.exists()
        assert user_file.read_text() == "x\n1\n"
        assert project_venv.exists()


def test_session_workspace_symlink_is_unlinked_without_deleting_target(tmp_path) -> None:
    external = tmp_path / "external-user-data"
    external.mkdir()
    marker = external / "keep.txt"
    marker.write_text("keep")

    with TestClient(create_app()) as client:
        session_id = client.post(
            "/api/chat/sessions",
            json={"title": "Symlink workspace"},
        ).json()["id"]
        workspace_link = workspaces_dir() / session_id
        workspace_link.symlink_to(external, target_is_directory=True)

        response = client.delete(f"/api/chat/sessions/{session_id}")

        assert response.status_code == 200, response.text
        assert not workspace_link.exists()
        assert marker.read_text() == "keep"
