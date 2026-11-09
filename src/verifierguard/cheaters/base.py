"""Cheater agents: small scripts that try to pass without doing the work."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from verifierguard.models import RunResult, Task
from verifierguard.runner import Runner


@dataclass(frozen=True)
class Attempt:
    label: str
    script: str


@dataclass
class CheaterResult:
    name: str
    succeeded: bool
    meaning: str
    attempts: list[dict[str, object]] = field(default_factory=list)
    evidence: str = ""
    inconclusive: bool = False  # verifier hit infrastructure errors, so 'blocked' is not trusted


class Cheater(ABC):
    name: str
    meaning: str  # what it means when this cheater succeeds

    @abstractmethod
    def attempts(self, task: Task) -> list[Attempt]: ...

    def succeeded(self, results: list[RunResult]) -> bool:
        return any(r.passed for r in results)

    def evidence(self, results: list[RunResult]) -> str:
        winners = [r.label for r in results if r.passed]
        return f"verifier gave credit on: {', '.join(winners)}" if winners else ""

    def run(self, task: Task, runner: Runner) -> CheaterResult:
        results = [runner.run(task, a.script, a.label) for a in self.attempts(task)]
        succeeded = self.succeeded(results)
        return CheaterResult(
            name=self.name,
            succeeded=succeeded,
            inconclusive=not succeeded and any(r.infra_failure for r in results),
            meaning=self.meaning,
            attempts=[
                {"label": r.label, "reward": r.reward, "agent_exit": r.agent_exit, "error": r.error}
                for r in results
            ],
            evidence=self.evidence(results),
        )
