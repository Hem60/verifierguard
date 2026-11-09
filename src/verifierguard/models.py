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

    def _section(self, name: str) -> dict[str, object]:
        value = self.config.get(name, {})
        return value if isinstance(value, dict) else {}

    def _seconds(self, section: str, key: str, default: int, cap: int) -> int:
        value = self._section(section).get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return min(int(value), cap)
        return default

    @property
    def docker_image(self) -> str | None:
        value = self._section("environment").get("docker_image")
        return value if isinstance(value, str) and value else None

    @property
    def memory(self) -> str | None:
        value = self._section("environment").get("memory")
        return value if isinstance(value, str) and value else None

    @property
    def agent_timeout(self) -> int:
        """Time allowed for the oracle solution (cheaters use a short fixed limit)."""
        return self._seconds("agent", "timeout_sec", 120, 1800)

    @property
    def verifier_timeout(self) -> int:
        return self._seconds("verifier", "timeout_sec", 300, 1800)

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
    infra_failure: bool = False  # verifier could not run properly (network etc.)

    @property
    def passed(self) -> bool:
        """The verifier gave any credit at all."""
        return self.reward is not None and self.reward > 0
