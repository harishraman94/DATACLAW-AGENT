"""Thin, machine-readable wrapper around Hermes' native batch runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from dataclaw_hermes.config import HERMES_COMPAT_VERSION, HermesConfig


def _dataset_items(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{path}:{line_number} is not valid JSON"
            ) from exc
        if not isinstance(item, dict) or not isinstance(
            item.get("prompt"), str
        ):
            raise ValueError(
                f"{path}:{line_number} must contain a string prompt"
            )
        items.append(item)
    if not items:
        raise ValueError(f"{path} contains no evaluation items")
    return items


def _records(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in paths:
        try:
            if path.suffix == ".jsonl":
                values = [
                    json.loads(line)
                    for line in path.read_text().splitlines()
                    if line.strip()
                ]
            else:
                value = json.loads(path.read_text())
                values = value if isinstance(value, list) else [value]
            for value in values:
                if isinstance(value, dict):
                    yield value
        except (OSError, ValueError, TypeError):
            continue


def _summarize_output(
    *,
    output_dir: Path,
    expected: int,
    return_code: int,
    elapsed_seconds: float,
    cancelled: bool,
    command: list[str],
) -> dict[str, Any]:
    files = sorted(
        [
            *output_dir.rglob("*.json"),
            *output_dir.rglob("*.jsonl"),
        ]
    ) if output_dir.exists() else []
    records = list(_records(files))
    completed = sum(
        1 for record in records if record.get("completed") is True
    )
    explicit_failures = sum(
        1
        for record in records
        if record.get("completed") is False or record.get("error")
    )
    partial = sum(1 for record in records if record.get("partial") is True)
    api_calls = sum(
        int(record.get("api_calls") or 0) for record in records
    )
    tool_stats: dict[str, dict[str, int]] = {}
    for record in records:
        for name, stats in (record.get("tool_stats") or {}).items():
            if not isinstance(stats, dict):
                continue
            aggregate = tool_stats.setdefault(
                str(name), {"count": 0, "success": 0, "failure": 0}
            )
            for key in aggregate:
                aggregate[key] += int(stats.get(key) or 0)
    failed = max(explicit_failures, len(records) - completed)
    missing = max(0, expected - len(records))
    return {
        "schemaVersion": 1,
        "harness": "hermes-native-batch",
        "hermesCompatibilityVersion": HERMES_COMPAT_VERSION,
        "status": (
            "cancelled"
            if cancelled
            else "failed"
            if return_code != 0 and not records
            else "partial_failure"
            if return_code != 0 or failed or missing or partial
            else "completed"
        ),
        "returnCode": return_code,
        "expectedItems": expected,
        "observedRecords": len(records),
        "completedItems": completed,
        "failedItems": failed,
        "partialItems": partial,
        "missingItems": missing,
        "failureRate": round((failed + missing) / expected, 6),
        "apiCalls": api_calls,
        "toolStatistics": tool_stats,
        "elapsedSeconds": round(elapsed_seconds, 3),
        "outputDirectory": str(output_dir),
        "outputFiles": [str(path) for path in files],
        "command": command,
        "dataclawGovernanceCoverage": False,
        "limitations": [
            "Pinned Hermes batch_runner.py assigns task_<index> IDs and does "
            "not create Dataclaw sessions/runs, so native batch results do "
            "not exercise the governed Dataclaw callback path."
        ],
    }


async def _run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    dataset = args.dataset.resolve()
    items = _dataset_items(dataset)
    hermes_root = args.hermes_root.resolve()
    runner = (hermes_root / args.runner).resolve()
    if not runner.is_file():
        raise FileNotFoundError(f"Hermes batch runner was not found: {runner}")
    output_dir = hermes_root / "data" / args.run_name
    command = [
        str(args.python),
        str(runner),
        f"--dataset_file={dataset}",
        f"--batch_size={args.batch_size}",
        f"--run_name={args.run_name}",
        f"--model={args.model}",
        f"--num_workers={args.num_workers}",
        f"--distribution={args.distribution}",
        f"--max_turns={args.max_turns}",
    ]
    if args.resume:
        command.append("--resume")
    environment = dict(os.environ)
    environment["HERMES_PROFILE"] = args.profile
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=hermes_root,
        env=environment,
    )
    cancelled = False
    try:
        return_code = await process.wait()
    except asyncio.CancelledError:
        cancelled = True
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
        return_code = 130
    summary = _summarize_output(
        output_dir=output_dir,
        expected=len(items),
        return_code=return_code,
        elapsed_seconds=time.monotonic() - started,
        cancelled=cancelled,
        command=command,
    )
    return return_code, summary


def _parser() -> argparse.ArgumentParser:
    config = HermesConfig.resolve()
    parser = argparse.ArgumentParser(
        description="Run a JSONL dataset through Hermes' native batch runner"
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--hermes-root", type=Path, required=True)
    parser.add_argument("--runner", default="batch_runner.py")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--model", default=config.model, required=not config.model)
    parser.add_argument("--profile", default=config.profile)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--num-workers", type=int, default=1)
    parser.add_argument("--distribution", default="default")
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--summary", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.batch_size < 1 or args.num_workers < 1 or args.max_turns < 1:
        raise SystemExit(
            "batch-size, num-workers, and max-turns must be positive"
        )
    try:
        return_code, summary = asyncio.run(_run(args))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    encoded = json.dumps(summary, indent=2)
    print(encoded)
    if args.summary is not None:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(encoded + "\n")
    raise SystemExit(return_code)


if __name__ == "__main__":
    main()
