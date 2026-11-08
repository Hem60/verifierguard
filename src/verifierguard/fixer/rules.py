"""Level 1: rule based gap explanations and fixes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from verifierguard.cheaters.base import CheaterResult
from verifierguard.static_checks import Finding

RESET_MARK = "# VerifierGuard: reset reward"
RESET_BLOCK = (
    f"{RESET_MARK} so nothing written by the agent can survive\n"
    "mkdir -p /logs/verifier\n"
    "rm -f /logs/verifier/reward.txt /logs/verifier/reward.json\n"
    "echo 0 > /logs/verifier/reward.txt\n"
)


@dataclass
class Fix:
    """A suggested change. `patch` edits a COPY of the task folder; None means advice only."""

    cheater: str  # which cheater the proof re-runs
    gap: str
    suggestion: str
    patch: Callable[[Path], None] | None = None
    source: str = "rule"


def reset_reward(task_root: Path) -> None:
    """Make test.sh start by setting the reward to 0 (idempotent)."""
    path = task_root / "tests" / "test.sh"
    text = path.read_text(encoding="utf-8")
    if RESET_MARK in text:
        return
    lines = text.splitlines(keepends=True)
    insert_at = 1 if lines and lines[0].startswith("#!") else 0
    lines.insert(insert_at, RESET_BLOCK)
    path.write_text("".join(lines), encoding="utf-8", newline="\n")


_ADVICE: dict[str, tuple[str, str]] = {
    "do_nothing": (
        "The verifier passes an environment where the agent did nothing.",
        "Check what the output contains, and fail when the expected file or result is missing.",
    ),
    "hard_code": (
        "The verifier accepted a made up value (it checks presence or a guessable value).",
        "Compute the right answer in the verifier, or use hidden test inputs the agent never sees.",
    ),
    "test_peek": (
        "Tests, answer key or solution can be found by the agent.",
        "Copy tests in only after the agent finishes, keep them out of the image, "
        "or run the verifier in a separate container.",
    ),
    "tamper": (
        "The agent can pre-write the reward file, and the verifier never overwrites it.",
        "Reset the reward to 0 at the start of test.sh (applied by the automatic patch), "
        "and ideally write the reward only from inside the verifier.",
    ),
}


def suggest_fixes(results: list[CheaterResult], findings: list[Finding]) -> list[Fix]:
    fixes: list[Fix] = []
    for res in results:
        if not res.succeeded:
            continue
        gap, suggestion = _ADVICE[res.name]
        patch = reset_reward if res.name == "tamper" else None
        fixes.append(Fix(res.name, gap, suggestion, patch))

    tamper_covered = any(f.cheater == "tamper" for f in fixes)
    for finding in findings:
        if finding.code == "VG005" and not tamper_covered:
            gap, suggestion = _ADVICE["tamper"]
            fixes.append(Fix("tamper", f"{finding.title}. {gap}", suggestion, reset_reward))
            tamper_covered = True
        elif finding.code == "VG010":
            gap, suggestion = _ADVICE["test_peek"]
            fixes.append(Fix("test_peek", f"{finding.title}. {gap}", suggestion, None))
    return fixes
