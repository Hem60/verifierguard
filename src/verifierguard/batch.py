"""Scan many task folders and save one CSV row each."""

from __future__ import annotations

import csv
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


def run_batch(root: Path, csv_path: Path, runner: Runner | None, propose_fixes: bool = False) -> int:
    """Returns how many tasks were scanned. A broken task becomes an error row, not a crash."""
    tasks = find_tasks(root)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for path in tasks:
            try:
                report = scan_task(load_task(path), runner, propose_fixes=propose_fixes)
                writer.writerow(row_for(report))
            except Exception as exc:  # noqa: BLE001 - keep scanning the rest
                kind = "task" if isinstance(exc, TaskError) else "scan"
                writer.writerow({"task": path.name, "error": f"{kind} error: {exc}"})
            fh.flush()
    return len(tasks)
