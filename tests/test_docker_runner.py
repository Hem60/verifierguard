"""Real container runs. Skipped when no Docker daemon is available."""

import pytest

from conftest import EXAMPLES, FIXTURES
from verifierguard.cheaters import DoNothing, HardCode, Tamper, TestPeek
from verifierguard.loader import load_task
from verifierguard.runner import DockerRunner, RunnerError

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def runner() -> DockerRunner:
    return DockerRunner()


def oracle(runner: DockerRunner, name: str, root=EXAMPLES):  # type: ignore[no-untyped-def]
    task = load_task(root / name)
    return task, runner.run(task, "#!/bin/bash\nbash /solution/solve.sh\n", "oracle", True)


def test_oracle_passes_on_both_examples(runner: DockerRunner) -> None:
    for name in ("weak_task", "strong_task"):
        _, res = oracle(runner, name)
        assert res.passed, res


def test_weak_task_is_cheatable(runner: DockerRunner) -> None:
    task = load_task(EXAMPLES / "weak_task")
    assert not DoNothing().run(task, runner).succeeded
    assert HardCode().run(task, runner).succeeded
    assert Tamper().run(task, runner).succeeded
    assert not TestPeek().run(task, runner).succeeded


def test_strong_task_resists_every_cheater(runner: DockerRunner) -> None:
    task = load_task(EXAMPLES / "strong_task")
    for cheater in (DoNothing(), HardCode(), TestPeek(), Tamper()):
        assert not cheater.run(task, runner).succeeded, cheater.name


def test_leaky_task_exposes_solution(runner: DockerRunner) -> None:
    task = load_task(FIXTURES / "leaky_task")
    res = TestPeek().run(task, runner)
    assert res.succeeded
    assert "solve.sh" in res.evidence


def test_build_failure_raises(make_task, runner: DockerRunner) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task(dockerfile="FROM debian:bookworm-slim\nRUN exit 3\n"))
    with pytest.raises(RunnerError):
        runner.build(task)
