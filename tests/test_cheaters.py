from conftest import FakeRunner
from verifierguard.cheaters import all_cheaters
from verifierguard.cheaters.hard_code import PLACEHOLDERS, HardCode
from verifierguard.cheaters.test_peek import MARKER, TestPeek
from verifierguard.loader import load_task
from verifierguard.runner import parse_reward


def test_four_cheaters() -> None:
    assert [c.name for c in all_cheaters()] == ["do_nothing", "hard_code", "test_peek", "tamper"]


def test_hard_code_scripts_cover_paths_and_values(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    attempts = HardCode().attempts(task)
    assert len(attempts) == len(PLACEHOLDERS)
    assert all("/app/answer.txt" in a.script for a in attempts)


def test_hard_code_fallback_path(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task(instruction="Do the thing.\n", test_sh="true\n"))
    assert "/app/answer.txt" in HardCode().attempts(task)[0].script


def test_cheater_succeeds_when_verifier_gives_credit(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    runner = FakeRunner(lambda *_: (1.0, ""))
    results = {c.name: c.run(task, runner) for c in all_cheaters()}
    assert results["do_nothing"].succeeded
    assert results["tamper"].succeeded
    assert "gave credit" in results["do_nothing"].evidence


def test_cheater_fails_when_verifier_refuses(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    runner = FakeRunner(lambda *_: (0.0, ""))
    for cheater in all_cheaters():
        res = cheater.run(task, runner)
        assert not res.succeeded
        assert res.evidence == ""


def test_peek_depends_on_exposure_marker(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    exposed = FakeRunner(lambda *_: (0.0, f"{MARKER}\n/app/solve.sh\n/app/expected.txt\n"))
    res = TestPeek().run(task, exposed)
    assert res.succeeded
    assert "/app/solve.sh" in res.evidence
    hidden = FakeRunner(lambda *_: (1.0, ""))
    assert not TestPeek().run(task, hidden).succeeded


def test_parse_reward() -> None:
    assert parse_reward("1\n") == 1.0
    assert parse_reward("0.5") == 0.5
    assert parse_reward('{"reward": 1}') == 1.0
    assert parse_reward('{"score": 0.25}') == 0.25
    assert parse_reward("garbage") is None
    assert parse_reward("{}") is None
    assert parse_reward('{"reward": true}') is None
