from __future__ import annotations

import json
from pathlib import Path

from verifierguard.scanner import ScanReport


def to_json(report: ScanReport) -> str:
    return json.dumps(report.to_dict(), indent=2)


def write_json(report: ScanReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(report) + "\n", encoding="utf-8")
