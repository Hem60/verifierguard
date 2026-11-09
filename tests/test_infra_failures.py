import pytest

from conftest import FakeRunner
from verifierguard.cheaters import DoNothing
from verifierguard.loader import load_task
from verifierguard.models import RunResult
from verifierguard.report import render_text
from verifierguard.runner import DockerRunner, looks_like_infra_failure
from verifierguard.scanner import BROKEN, INCONCLUSIVE, SOLID, decide_verdict, scan_task


def result(reward: float | None, log: str = "", error: str | None = None) -> RunResult:
    return RunResult(label="x", reward=reward, verifier_log=log, error=error)


def test_infra_detection() -> None:
    assert looks_like_infra_failure(result(None, "curl: (22) The requested URL returned error: 504"))
    assert looks_like_infra_failure(result(0.0, "/tests/test.sh: line 19: uvx: command not found"))
    assert looks_like_infra_failure(result(None, "", error="docker exec timed out"))
    assert not looks_like_infra_failure(result(0.0, "AssertionError: wrong answer"))
    assert not looks_like_infra_failure(result(1.0, "failed to download but passed anyway"))


class Scripted(DockerRunner):
    def __init__(self, outcomes: list[RunResult]) -> None:
        super().__init__()
        self.outcomes = outcomes
        self.runs = 0

    def _run_once(self, task, script, label, with_solution=False):  # type: ignore[no-untyped-def]
        self.runs += 1
        return self.outcomes.pop(0)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("verifierguard.runner.time.sleep", lambda _s: None)


def test_retry_until_infra_clears(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    bad = result(0.0, "failed to download uv")
    runner = Scripted([bad, bad, result(1.0)])
    out = runner.run(task, "true", "x")
    assert out.passed and not out.infra_failure and runner.runs == 3


def test_gives_up_and_flags_infra(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    bad = result(0.0, "Could not resolve host")
    runner = Scripted([bad, bad, bad])
    out = runner.run(task, "true", "x")
    assert out.infra_failure and runner.runs == 3


def test_genuine_failure_is_not_retried(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    runner = Scripted([result(0.0, "AssertionError")])
    out = runner.run(task, "true", "x")
    assert not out.passed and not out.infra_failure and runner.runs == 1


def test_cheater_inconclusive_when_infra(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())

    class Infra(FakeRunner):
        def run(self, task, script, label, with_solution=False):  # type: ignore[no-untyped-def]
            r = super().run(task, script, label, with_solution)
            r.infra_failure = not with_solution
            return r

    res = DoNothing().run(task, Infra(lambda *_: (0.0, "")))
    assert res.inconclusive and not res.succeeded


def test_verdicts() -> None:
    assert decide_verdict([], [], False, oracle_infra=True) == INCONCLUSIVE
    assert decide_verdict([], [], False) == BROKEN
    assert decide_verdict([], [], True) == SOLID


def test_scan_reports_inconclusive(make_task) -> None:  # type: ignore[no-untyped-def]
    sh = (
        "#!/bin/bash\necho 0 > /logs/verifier/reward.txt\n"
        "if grep -q 1 /app/a; then echo 1 > /logs/verifier/reward.txt; fi\n"
    )
    task = load_task(make_task(test_sh=sh))

    class Flaky(FakeRunner):
        def run(self, task, script, label, with_solution=False):  # type: ignore[no-untyped-def]
            r = super().run(task, script, label, with_solution)
            r.infra_failure = not with_solution
            return r

    report = scan_task(task, Flaky(lambda t, s, label, sol: (1.0 if sol else 0.0, "")))
    assert report.verdict == INCONCLUSIVE
    assert "INCONCLUSIVE" in render_text(report)
    assert report.to_dict()["oracle_infra_failure"] is False
