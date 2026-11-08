"""Plain data objects shared across the package."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Task:
    """A Harbor style task folder, read from disk."""

    path: Path
    name: str
    instruction: str
    dockerfile: str
    workdir: str
    verifier_files: dict[str, str]
    has_solution: bool
    config: dict[str, object] = field(default_factory=dict)

    @property
    def env_dir(self) -> Path:
        return self.path / "environment"

    @property
    def tests_dir(self) -> Path:
        return self.path / "tests"

    @property
    def solution_dir(self) -> Path:
        return self.path / "solution"

    @property
    def verifier_text(self) -> str:
        return "\n".join(self.verifier_files.values())


@dataclass
class RunResult:
    """Outcome of one container run: agent script, then the verifier."""

    label: str
    reward: float | None = None
    agent_exit: int | None = None
    agent_log: str = ""
    verifier_log: str = ""
    error: str | None = None

    @property
    def passed(self) -> bool:
        """The verifier gave any credit at all."""
        return self.reward is not None and self.reward > 0
