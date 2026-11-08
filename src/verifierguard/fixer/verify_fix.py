"""Level 3: prove a fix on a copy of the task."""

from __future__ import annotations

import difflib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from verifierguard.cheaters import all_cheaters
from verifierguard.fixer.rules import Fix
from verifierguard.loader import load_task
from verifierguard.models import RunResult, Task
from verifierguard.runner import Runner

VERIFIED = "verified"
NOT_VERIFIED = "not_verified"
ADVICE_ONLY = "advice_only"

ORACLE_SCRIPT = "#!/bin/bash\nbash /solution/solve.sh\n"
_DIFF_DIRS = ("tests", "environment")


@dataclass
class FixProof:
    status: str
    reason: str
    diff: str = ""
    cheater_failed_after: bool | None = None
    oracle_passed_after: bool | None = None

    @property
    def verified(self) -> bool:
        return self.status == VERIFIED


def run_oracle(task: Task, runner: Runner) -> RunResult:
    return runner.run(task, ORACLE_SCRIPT, "oracle", with_solution=True)


def make_diff(before: Path, after: Path) -> str:
    chunks: list[str] = []
    for sub in _DIFF_DIRS:
        old_root, new_root = before / sub, after / sub
        names = {p.relative_to(root).as_posix() for root in (old_root, new_root)
                 if root.is_dir() for p in root.rglob("*") if p.is_file()}  # fmt: skip
        for name in sorted(names):
            old = old_root / name
            new = new_root / name
            old_lines = (
                old.read_text(encoding="utf-8", errors="replace").splitlines(True) if old.is_file() else []
            )
            new_lines = (
                new.read_text(encoding="utf-8", errors="replace").splitlines(True) if new.is_file() else []
            )
            chunks.extend(difflib.unified_diff(
                old_lines, new_lines, f"a/{sub}/{name}", f"b/{sub}/{name}"))  # fmt: skip
    return "".join(chunks)


def prove_fix(task: Task, fix: Fix, runner: Runner) -> FixProof:
    """Apply the fix to a copy, then require: cheater fails AND correct solution passes."""
    if fix.patch is None:
        return FixProof(ADVICE_ONLY, "no automatic patch exists for this gap: please review by hand")
    if not task.has_solution:
        return FixProof(NOT_VERIFIED, "task has no solution/solve.sh, so the fix cannot be proven")

    cheater = next((c for c in all_cheaters() if c.name == fix.cheater), None)
    if cheater is None:
        return FixProof(NOT_VERIFIED, f"unknown cheater {fix.cheater!r}")

    with tempfile.TemporaryDirectory(prefix="vg_copy_") as tmp:
        copy_root = Path(tmp) / task.path.name
        shutil.copytree(task.path, copy_root)
        fix.patch(copy_root)
        diff = make_diff(task.path, copy_root)
        patched = load_task(copy_root)

        cheat = cheater.run(patched, runner)
        oracle = run_oracle(patched, runner)

    cheater_failed = not cheat.succeeded
    oracle_ok = oracle.passed
    if cheater_failed and oracle_ok:
        return FixProof(VERIFIED, "cheater now fails and the correct solution still passes",
                        diff, True, True)  # fmt: skip
    problems = []
    if not cheater_failed:
        problems.append(f"the {fix.cheater} cheater still passes")
    if not oracle_ok:
        problems.append("the correct solution no longer passes")
    return FixProof(NOT_VERIFIED, "fix suggested but not verified: " + " and ".join(problems)
                    + ". Please review by hand.", diff, cheater_failed, oracle_ok)  # fmt: skip
