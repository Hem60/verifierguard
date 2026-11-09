"""Scan many task folders and save one CSV row each."""

from __future__ import annotations

import csv
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from verifierguard.loader import REQUIRED, TaskError, load_task
from verifierguard.runner import Runner
from verifierguard.scanner import ScanReport, scan_task

COLUMNS = [
    "task", "verdict", "score", "oracle_passed", "cheaters_passed",
    "static_findings", "fixes_verified", "error",
]  # fmt: skip


def find_tasks(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir() and all((p / rel).is_file() for rel in REQUIRED))


def row_for(report: ScanReport) -> dict[str, object]:
    return {
        "task": report.task,
        "verdict": report.verdict,
        "score": report.score,
        "oracle_passed": "" if report.oracle_passed is None else report.oracle_passed,
        "cheaters_passed": ";".join(report.cheaters_passed),
        "static_findings": ";".join(f.code for f in report.findings),
        "fixes_verified": sum(1 for f in report.fixes if f.proof.verified),
        "error": "",
    }


def _scan_one(path: Path, runner: Runner | None, propose_fixes: bool, cleanup: bool) -> dict[str, object]:
    """Scan one folder. A broken task becomes an error row, not a crash."""
    try:
        task = load_task(path)
        try:
            return row_for(scan_task(task, runner, propose_fixes=propose_fixes))
        finally:
            remove = getattr(runner, "cleanup", None)
            if cleanup and callable(remove):
                remove(task)
    except Exception as exc:  # noqa: BLE001 - keep scanning the rest
        kind = "task" if isinstance(exc, TaskError) else "scan"
        return {"task": path.name, "error": f"{kind} error: {exc}"}


def run_batch(
    root: Path,
    csv_path: Path,
    runner: Runner | None,
    propose_fixes: bool = False,
    *,
    only: set[str] | None = None,
    jobs: int = 1,
    cleanup: bool = False,
    on_row: Callable[[dict[str, object]], None] | None = None,
) -> int:
    """Scan task folders and write one CSV row each. Returns how many were scanned."""
    tasks = [p for p in find_tasks(root) if only is None or p.name in only]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        with ThreadPoolExecutor(max_workers=max(jobs, 1)) as pool:
            futures = [pool.submit(_scan_one, p, runner, propose_fixes, cleanup) for p in tasks]
            for future in as_completed(futures):
                row = future.result()
                writer.writerow(row)
                fh.flush()
                if on_row is not None:
                    on_row(row)
    return len(tasks)
