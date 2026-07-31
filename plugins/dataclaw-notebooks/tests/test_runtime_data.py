"""Tests for the dataclaw_data package injected into notebook kernels."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import duckdb
import pytest


@pytest.fixture
def runtime_data_module():
    package_path = (
        Path(__file__).parents[1]
        / "dataclaw_notebooks"
        / "runtime_packages"
        / "dataclaw_data"
        / "__init__.py"
    )
    spec = importlib.util.spec_from_file_location("runtime_dataclaw_data", package_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(
        self,
        *,
        content: bytes = b"",
        body: dict[str, Any] | None = None,
        status_code: int = 200,
    ) -> None:
        self._content = content
        self._body = body or {}
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = "" if self.ok else str(self._body)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self._content), chunk_size):
            yield self._content[offset : offset + chunk_size]

    def json(self) -> dict[str, Any]:
        return self._body


def test_get_dataframe_without_n_rows_uses_full_export(
    runtime_data_module,
    monkeypatch,
    tmp_path,
):
    source_csv = tmp_path / "source.csv"
    source_csv.write_text("id,value\n1,10\n2,20\n3,30\n")
    source_parquet = tmp_path / "source.parquet"
    conn = duckdb.connect()
    try:
        conn.sql(
            f"COPY (SELECT * FROM read_csv_auto('{source_csv.as_posix()}')) "
            f"TO '{source_parquet.as_posix()}' (FORMAT PARQUET)"
        )
    finally:
        conn.close()
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(content=source_parquet.read_bytes())

    monkeypatch.setattr(runtime_data_module.requests, "post", fake_post)
    monkeypatch.setenv("DATACLAW_SESSION_ID", "session-1")

    frame = runtime_data_module.get_dataframe("dataset-1", table_name="source.csv")

    assert len(frame) == 3
    assert frame.attrs["dataclaw_access_mode"] == "full"
    assert frame.attrs["dataclaw_truncated"] is False
    assert calls[0][0].endswith("/api/data/dataframe/export")
    assert calls[0][1]["stream"] is True
    assert calls[0][1]["json"]["session_id"] == "session-1"


def test_get_dataframe_with_n_rows_uses_bounded_preview(
    runtime_data_module,
    monkeypatch,
):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            body={
                "columns": ["id"],
                "rows": [{"id": 1}, {"id": 2}],
                "truncated": True,
                "row_limit": 2,
            }
        )

    monkeypatch.setattr(runtime_data_module.requests, "post", fake_post)
    monkeypatch.setenv("DATACLAW_SESSION_ID", "session-1")

    with pytest.warns(RuntimeWarning, match="limited this preview"):
        frame = runtime_data_module.get_dataframe(
            "dataset-1",
            table_name="source.csv",
            n_rows=2,
        )

    assert len(frame) == 2
    assert frame.attrs["dataclaw_access_mode"] == "preview"
    assert frame.attrs["dataclaw_truncated"] is True
    assert calls[0][0].endswith("/api/data/dataframe")
    assert not calls[0][0].endswith("/export")


def test_get_dataframe_rejects_non_positive_preview_limit(runtime_data_module):
    with pytest.raises(ValueError, match="greater than zero"):
        runtime_data_module.get_dataframe(
            "dataset-1",
            table_name="source.csv",
            n_rows=0,
        )
