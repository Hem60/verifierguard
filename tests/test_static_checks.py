from conftest import EXAMPLES
from verifierguard.loader import load_task
from verifierguard.static_checks import run_static_checks


def codes(make_task, **kw) -> set[str]:  # type: ignore[no-untyped-def]
    return {f.code for f in run_static_checks(load_task(make_task(**kw)))}


def test_strong_example_is_clean() -> None:
    assert run_static_checks(load_task(EXAMPLES / "strong_task")) == []


def test_weak_example_flags_existence_and_no_reset() -> None:
    found = {f.code for f in run_static_checks(load_task(EXAMPLES / "weak_task"))}
    assert found == {"VG005", "VG006"}


def test_no_reward_written(make_task) -> None:  # type: ignore[no-untyped-def]
    assert "VG001" in codes(make_task, test_sh="#!/bin/bash\necho hello\n")


def test_unconditional_reward(make_task) -> None:  # type: ignore[no-untyped-def]
    assert "VG002" in codes(make_task, test_sh="#!/bin/bash\necho 1 > /logs/verifier/reward.txt\n")


def test_bare_exit_zero(make_task) -> None:  # type: ignore[no-untyped-def]
    assert "VG003" in codes(make_task, test_sh="#!/bin/bash\nreward=1\nexit 0\n")


def test_swallowed_failures(make_task) -> None:  # type: ignore[no-untyped-def]
    sh = "#!/bin/bash\npytest /tests || true\nif true; then echo 1 > /logs/verifier/reward.txt; fi\n"
    assert "VG004" in codes(make_task, test_sh=sh)


def test_python_without_assert(make_task) -> None:  # type: ignore[no-untyped-def]
    found = codes(make_task, extra_tests={"test_x.py": "def test_a():\n    x = 1\n"})
    assert "VG007" in found


def test_python_empty_test(make_task) -> None:  # type: ignore[no-untyped-def]
    body = "def test_a():\n    pass\n\ndef test_b():\n    assert 1 == 1\n"
    assert "VG008" in codes(make_task, extra_tests={"test_x.py": body})


def test_python_with_assert_is_fine(make_task) -> None:  # type: ignore[no-untyped-def]
    found = codes(make_task, extra_tests={"test_x.py": "def test_a():\n    assert 2 == 2\n"})
    assert not {"VG007", "VG008"} & found


def test_dockerfile_copies_tests(make_task) -> None:  # type: ignore[no-untyped-def]
    found = codes(make_task, dockerfile="FROM x\nCOPY tests /app/tests\n")
    assert "VG010" in found
    assert "VG010" not in codes(make_task, dockerfile="FROM x\nCOPY data.csv /app/\n")
