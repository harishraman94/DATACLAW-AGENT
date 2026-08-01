"""MLflow experiment tracking tools."""

from __future__ import annotations

import logging
import shutil
from typing import Any

from dataclaw.config.paths import plugin_data_dir
from dataclaw.mlflow_compat import MLFLOW_VERSION

logger = logging.getLogger(__name__)

_TRACKING_URI: str | None = None


def _get_tracking_uri() -> str:
    global _TRACKING_URI
    db_path = plugin_data_dir("plans") / "mlflow.db"
    expected = f"sqlite:///{db_path}"
    if _TRACKING_URI != expected:
        _TRACKING_URI = expected
    return _TRACKING_URI


def _client():
    import mlflow

    if mlflow.__version__ != MLFLOW_VERSION:
        raise RuntimeError(
            "DataClaw's MLflow runtime is inconsistent: "
            f"expected {MLFLOW_VERSION}, found {mlflow.__version__}. "
            "Synchronize the locked environment before using experiment tracking."
        )
    mlflow.set_tracking_uri(_get_tracking_uri())
    return mlflow.tracking.MlflowClient(_get_tracking_uri())


def get_or_create_experiment(session_id: str) -> str:
    """Get or create an MLflow experiment for a session."""
    client = _client()
    exp_name = f"dataclaw-{session_id}"
    exp = client.get_experiment_by_name(exp_name)
    if exp:
        return exp.experiment_id
    artifacts_dir = str(plugin_data_dir("plans") / "mlflow_artifacts")
    return client.create_experiment(exp_name, artifact_location=artifacts_dir)


def delete_session_experiment(session_id: str) -> dict[str, Any]:
    """Delete a session's MLflow runs/artifacts and retire its experiment."""
    if not session_id:
        return {"removed": False}
    try:
        client = _client()
        experiment = client.get_experiment_by_name(f"dataclaw-{session_id}")
        if experiment is None:
            return {"removed": False}

        run_ids: list[str] = []
        try:
            from mlflow.entities import ViewType

            runs = client.search_runs(
                experiment_ids=[experiment.experiment_id],
                max_results=100_000,
                run_view_type=ViewType.ALL,
            )
            run_ids = [str(run.info.run_id) for run in runs]
        except Exception:
            logger.debug("Could not enumerate MLflow runs during cleanup", exc_info=True)

        client.delete_experiment(experiment.experiment_id)

        # MlflowClient deletion is recoverable (lifecycle_stage=deleted).
        # Session deletion is explicitly permanent, so run MLflow's own GC
        # implementation for this exact experiment to remove its metadata and
        # artifacts rather than leaving a restorable hidden record.
        from mlflow.cli import _gc_tracking_resources, _get_store

        backend_store = _get_store(_get_tracking_uri(), None)
        if not hasattr(backend_store, "_hard_delete_experiment"):
            raise RuntimeError("MLflow backend does not support permanent experiment deletion")
        _gc_tracking_resources(
            backend_store=backend_store,
            run_ids=None,
            experiment_ids=[str(experiment.experiment_id)],
            logged_model_ids=None,
            older_than=None,
            time_delta=0,
            skip_experiments=False,
            skip_logged_models=True,
        )

        artifacts_root = plugin_data_dir("plans") / "mlflow_artifacts"
        for run_id in run_ids:
            run_dir = artifacts_root / run_id
            if run_dir.parent == artifacts_root and run_dir.exists():
                shutil.rmtree(run_dir)
        return {
            "removed": True,
            "experiment_id": experiment.experiment_id,
            "removed_run_artifacts": len(run_ids),
            "permanent": True,
        }
    except Exception:
        # MLflow is optional. If it is installed and has a matching experiment,
        # failures must abort session deletion rather than leave hidden state.
        logger.exception("Failed to delete MLflow experiment for %s", session_id)
        raise


def _serialize(val: Any) -> Any:
    if val is None or isinstance(val, (int, float, str, bool)):
        return val
    return str(val)


def session_run_metadata(session_id: str, *, max_results: int = 50) -> list[dict[str, Any]]:
    """Synchronous, failure-tolerant run metadata for a session's experiment.

    Returns only what reproducibility checks need (params/metrics/tags — no
    artifact listing), and returns [] on any failure so deterministic review
    checks never break when MLflow is unavailable.
    """
    if not session_id:
        return []
    try:
        client = _client()
        exp = client.get_experiment_by_name(f"dataclaw-{session_id}")
        if not exp:
            return []
        from mlflow.entities import ViewType

        runs = client.search_runs(
            experiment_ids=[exp.experiment_id],
            order_by=["start_time DESC"],
            max_results=max_results,
            run_view_type=ViewType.ACTIVE_ONLY,
        )
        return [
            {
                "run_id": run.info.run_id,
                "status": run.info.status,
                "params": {k: _serialize(v) for k, v in run.data.params.items()},
                "metrics": {k: _serialize(v) for k, v in run.data.metrics.items()},
                "tags": dict(run.data.tags),
            }
            for run in runs
        ]
    except Exception:
        return []


async def query_mlflow_runs(
    *,
    session_id: str = "",
    **kw: Any,
) -> dict[str, Any]:
    """Query MLflow runs for a session."""
    if not session_id:
        return {"runs": [], "error": "session_id required"}

    try:
        client = _client()
        exp_name = f"dataclaw-{session_id}"
        exp = client.get_experiment_by_name(exp_name)
        if not exp:
            return {"runs": [], "experiment": None}

        from mlflow.entities import ViewType
        runs = client.search_runs(
            experiment_ids=[exp.experiment_id],
            order_by=["start_time DESC"],
            max_results=50,
            run_view_type=ViewType.ACTIVE_ONLY,
        )

        result = []
        for run in runs:
            # List artifacts for this run
            artifacts = []
            try:
                for artifact in client.list_artifacts(run.info.run_id):
                    artifacts.append({"path": artifact.path, "size": artifact.file_size, "is_dir": artifact.is_dir})
            except Exception:
                pass

            # Get dataset inputs if available
            datasets = []
            try:
                if hasattr(run, 'inputs') and run.inputs and hasattr(run.inputs, 'dataset_inputs'):
                    for ds_input in run.inputs.dataset_inputs:
                        ds = ds_input.dataset
                        datasets.append({"name": ds.name, "digest": ds.digest, "source_type": ds.source_type})
            except Exception:
                pass

            result.append({
                "run_id": run.info.run_id,
                "status": run.info.status,
                "start_time": run.info.start_time,
                "end_time": run.info.end_time,
                "params": {k: _serialize(v) for k, v in run.data.params.items()},
                "metrics": {k: _serialize(v) for k, v in run.data.metrics.items()},
                "tags": dict(run.data.tags),
                "artifacts": artifacts,
                "datasets": datasets,
            })

        return {"runs": result, "experiment_id": exp.experiment_id}
    except Exception as e:
        logger.exception("Failed to query MLflow runs")
        return {"runs": [], "error": str(e)}


async def query_mlflow_runs_for_project(
    *,
    project_id: str,
) -> list[dict[str, Any]]:
    """Query MLflow runs across all sessions belonging to a project."""
    from dataclaw.storage.sessions import list_sessions

    sessions = await list_sessions(project_id)
    experiments: list[dict[str, Any]] = []

    for sess in sessions:
        sid = sess.get("id", "")
        if not sid:
            continue
        result = await query_mlflow_runs(session_id=sid)
        runs = result.get("runs", [])
        if runs or result.get("experiment_id"):
            experiments.append({
                "session_id": sid,
                "session_title": sess.get("title", sid[:12]),
                "experiment_id": result.get("experiment_id"),
                "runs": runs,
            })

    return experiments
