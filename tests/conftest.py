from __future__ import annotations

from pathlib import Path

import pytest

from verifierguard.models import RunResult, Task
from verifierguard.runner import docker_available

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

_DOCKER = docker_available()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _DOCKER:
        return
    skip = pytest.mark.skip(reason="Docker daemon not available")
    for item in items:
        if "docker" in item.keywords:
            item.add_marker(skip)


class FakeRunner:
    """Scripted runner: returns a reward chosen by a function of the script text."""

    def __init__(self, decide) -> None:  # type: ignore[no-untyped-def]
        self.decide = decide
        self.calls: list[tuple[str, bool]] = []

    def run(self, task: Task, script: str, label: str, with_solution: bool = False) -> RunResult:
        self.calls.append((label, with_solution))
        reward, log = self.decide(task, script, label, with_solution)
        return RunResult(label=label, reward=reward, agent_exit=0, agent_log=log)


@pytest.fixture
def make_task(tmp_path: Path):  # type: ignore[no-untyped-def]
    counter = {"n": 0}

    def _make(
        test_sh: str = "#!/bin/bash\necho 1 > /logs/verifier/reward.txt\n",
        instruction: str = "Write the total to /app/answer.txt\n",
        dockerfile: str = "FROM debian:bookworm-slim\nWORKDIR /app\n",
        solution: bool = True,
        extra_tests: dict[str, str] | None = None,
    ) -> Path:
        counter["n"] += 1
        root = tmp_path / ("task" if counter["n"] == 1 else f"task{counter['n']}")
        (root / "environment").mkdir(parents=True)
        (root / "tests").mkdir()
        (root / "instruction.md").write_text(instruction)
        (root / "environment" / "Dockerfile").write_text(dockerfile)
        (root / "tests" / "test.sh").write_text(test_sh, newline="\n")
        for name, body in (extra_tests or {}).items():
            (root / "tests" / name).write_text(body)
        if solution:
            (root / "solution").mkdir()
            (root / "solution" / "solve.sh").write_text("#!/bin/bash\ntrue\n", newline="\n")
        return root

    return _make
