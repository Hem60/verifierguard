"""Orchestrates one scan: oracle, cheaters, static checks, score, fixes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from verifierguard.cheaters import all_cheaters
from verifierguard.cheaters.base import Cheater, CheaterResult
from verifierguard.fixer.llm_fix import Caller, gemini_call, propose_fix
from verifierguard.fixer.rules import Fix, suggest_fixes
from verifierguard.fixer.verify_fix import FixProof, prove_fix, run_oracle
from verifierguard.models import Task
from verifierguard.runner import Runner
from verifierguard.static_checks import PENALTY, Finding, run_static_checks

CHEATER_PENALTY = {"do_nothing": 40, "hard_code": 30, "tamper": 30, "test_peek": 20}

WEAK, SOLID, BROKEN = "weak", "solid", "broken"


@dataclass
class FixOutcome:
    fix: Fix
    proof: FixProof

    def to_dict(self) -> dict[str, object]:
        return {
            "cheater": self.fix.cheater,
            "source": self.fix.source,
            "gap": self.fix.gap,
            "suggestion": self.fix.suggestion,
            "status": self.proof.status,
            "reason": self.proof.reason,
            "diff": self.proof.diff,
        }


@dataclass
class ScanReport:
    task: str
    dynamic: bool
    oracle_passed: bool | None
    cheaters: list[CheaterResult] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    fixes: list[FixOutcome] = field(default_factory=list)
    score: int = 100
    verdict: str = SOLID

    @property
    def cheaters_passed(self) -> list[str]:
        return [c.name for c in self.cheaters if c.succeeded]

    def to_dict(self) -> dict[str, object]:
        return {
            "task": self.task,
            "verdict": self.verdict,
            "score": self.score,
            "dynamic": self.dynamic,
            "oracle_passed": self.oracle_passed,
            "cheaters": [asdict(c) for c in self.cheaters],
            "cheaters_passed": self.cheaters_passed,
            "static_findings": [asdict(f) for f in self.findings],
            "fixes": [f.to_dict() for f in self.fixes],
            "note": "A clean scan means no known gap, not no gap.",
        }


def compute_score(cheaters: list[CheaterResult], findings: list[Finding]) -> int:
    score = 100
    score -= sum(CHEATER_PENALTY.get(c.name, 20) for c in cheaters if c.succeeded)
    score -= sum(PENALTY[f.severity] for f in findings)
    return max(score, 0)


def decide_verdict(cheaters: list[CheaterResult], findings: list[Finding], oracle_passed: bool | None) -> str:
    if oracle_passed is False:
        return BROKEN
    if any(c.succeeded for c in cheaters) or any(f.severity == "high" for f in findings):
        return WEAK
    return SOLID


def scan_task(
    task: Task,
    runner: Runner | None,
    *,
    cheaters: list[Cheater] | None = None,
    propose_fixes: bool = True,
    use_llm: bool = False,
    llm_call: Caller = gemini_call,
) -> ScanReport:
    """Scan a task. With runner=None only the static checks run."""
    findings = run_static_checks(task)
    report = ScanReport(task=task.name, dynamic=runner is not None, oracle_passed=None)
    report.findings = findings

    if runner is not None:
        if task.has_solution:
            report.oracle_passed = run_oracle(task, runner).passed
        if report.oracle_passed is not False:
            for cheater in cheaters if cheaters is not None else all_cheaters():
                report.cheaters.append(cheater.run(task, runner))

    report.score = compute_score(report.cheaters, findings)
    report.verdict = decide_verdict(report.cheaters, findings, report.oracle_passed)

    if runner is not None and propose_fixes and report.verdict == WEAK:
        fixes = suggest_fixes(report.cheaters, findings)
        if use_llm:
            for res in report.cheaters:
                if res.succeeded and not any(f.cheater == res.name and f.patch for f in fixes):
                    try:
                        llm = propose_fix(task, res, llm_call)
                    except RuntimeError:
                        llm = None
                    if llm is not None:
                        fixes.append(llm)
        report.fixes = [FixOutcome(fix, prove_fix(task, fix, runner)) for fix in fixes]
    return report
