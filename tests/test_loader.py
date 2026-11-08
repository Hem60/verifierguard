import pytest

from verifierguard.loader import TaskError, candidate_output_paths, load_task


def test_load_example(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    assert task.name == "task"
    assert task.workdir == "/app"
    assert task.has_solution
    assert "test.sh" in task.verifier_files


def test_workdir_taken_from_dockerfile(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task(dockerfile="FROM x\nWORKDIR /one\nWORKDIR /work\n"))
    assert task.workdir == "/work"


def test_missing_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TaskError, match="missing required files"):
        load_task(tmp_path)


def test_not_a_directory(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(TaskError, match="not a directory"):
        load_task(tmp_path / "nope")


def test_bad_toml(make_task) -> None:  # type: ignore[no-untyped-def]
    root = make_task()
    (root / "task.toml").write_text("this is = = bad")
    with pytest.raises(TaskError, match="bad task.toml"):
        load_task(root)


def test_good_toml_and_no_solution(make_task) -> None:  # type: ignore[no-untyped-def]
    root = make_task(solution=False)
    (root / "task.toml").write_text('version = "1.0"\n')
    task = load_task(root)
    assert task.config == {"version": "1.0"}
    assert not task.has_solution


def test_output_paths(make_task) -> None:  # type: ignore[no-untyped-def]
    root = make_task(
        instruction="Save to /app/out/result.json and also summary.txt. See instruction.md.\n",
        test_sh="cat /tests/expected.txt /logs/verifier/reward.txt /app/result2.csv\n",
    )
    paths = candidate_output_paths(load_task(root))
    assert "/app/out/result.json" in paths
    assert "/app/summary.txt" in paths
    assert "/app/result2.csv" in paths
    assert not any(p.startswith(("/tests", "/logs")) for p in paths)
    assert "/app/instruction.md" not in paths
