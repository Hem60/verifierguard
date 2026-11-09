import csv
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import EXAMPLES, FakeRunner
from verifierguard.batch import run_batch
from verifierguard.cli import app
from verifierguard.loader import load_task
from verifierguard.runner import DockerRunner, stage_dir


def with_config(make_task, toml: str):  # type: ignore[no-untyped-def]
    root = make_task()
    (root / "task.toml").write_text(toml)
    return load_task(root)


def test_task_config_values(make_task) -> None:  # type: ignore[no-untyped-def]
    task = with_config(
        make_task,
        '[environment]\ndocker_image = "x/y:1"\nmemory = "4G"\n'
        "[agent]\ntimeout_sec = 900.0\n[verifier]\ntimeout_sec = 99999\n",
    )
    assert task.docker_image == "x/y:1" and task.memory == "4G"
    assert task.agent_timeout == 900
    assert task.verifier_timeout == 1800  # capped


def test_task_config_defaults(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    assert task.docker_image is None and task.memory is None
    assert (task.agent_timeout, task.verifier_timeout) == (120, 300)
    bad = with_config(make_task, 'environment = "oops"\n[agent]\ntimeout_sec = true\n')
    assert bad.docker_image is None and bad.agent_timeout == 120


def test_stage_dir_converts_crlf(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.sh").write_bytes(b"#!/bin/bash\r\necho hi\r\n")
    (src / "data.txt").write_bytes(b"keep\r\n")
    out = stage_dir(src, tmp_path / "out")
    assert (out / "a.sh").read_bytes() == b"#!/bin/bash\necho hi\n"
    assert (out / "data.txt").read_bytes() == b"keep\r\n"
    assert (src / "a.sh").read_bytes().count(b"\r") == 2  # original untouched


class Recorder(DockerRunner):
    def __init__(self, fail_pull: bool = False, **kw) -> None:  # type: ignore[no-untyped-def]
        super().__init__(**kw)
        self.calls: list[tuple[str, ...]] = []
        self.fail_pull = fail_pull

    def _cmd(self, *args: str, timeout: int, check: bool = False):  # type: ignore[no-untyped-def]
        self.calls.append(args)
        code = 1 if (args[0] == "pull" and self.fail_pull) else 0
        return subprocess.CompletedProcess(args, code, "", "")


def test_prebuilt_pulls_and_cleans_up(make_task) -> None:  # type: ignore[no-untyped-def]
    task = with_config(make_task, '[environment]\ndocker_image = "x/y:1"\n')
    runner = Recorder(prebuilt=True)
    assert runner.build(task) == "x/y:1"
    assert runner.build(task) == "x/y:1"  # cached: one pull only
    assert [c[0] for c in runner.calls].count("pull") == 1
    runner.cleanup(task)
    assert runner.calls[-1] == ("rmi", "-f", "x/y:1")
    runner.cleanup(task)  # second cleanup is a no-op
    assert runner.calls[-1][0] == "rmi" and [c[0] for c in runner.calls].count("rmi") == 1


def test_prebuilt_falls_back_to_build(make_task) -> None:  # type: ignore[no-untyped-def]
    task = with_config(make_task, '[environment]\ndocker_image = "x/y:1"\n')
    runner = Recorder(prebuilt=True, fail_pull=True)
    tag = runner.build(task)
    assert tag.startswith("vg-") and runner.calls[-1][0] == "build"


def test_batch_only_jobs_cleanup(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "tasks"
    for name in ("a", "b", "c"):
        shutil.copytree(EXAMPLES / "weak_task", root / name)
    cleaned: list[str] = []

    class R(FakeRunner):
        def cleanup(self, task) -> None:  # type: ignore[no-untyped-def]
            cleaned.append(task.name)

    runner = R(lambda t, s, label, sol: (1.0 if sol else 0.0, ""))
    seen: list[str] = []
    out = tmp_path / "o.csv"
    n = run_batch(
        root, out, runner, only={"a", "c"}, jobs=2, cleanup=True, on_row=lambda r: seen.append(str(r["task"]))
    )
    assert n == 2
    rows = list(csv.DictReader(out.open()))
    assert sorted(r["task"] for r in rows) == ["a", "c"]
    assert sorted(cleaned) == ["a", "c"] and sorted(seen) == ["a", "c"]
    assert all(r["verdict"] == "solid" or r["verdict"] == "weak" for r in rows)


def test_cli_batch_only_file(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "tasks"
    shutil.copytree(EXAMPLES / "weak_task", root / "weak_task")
    shutil.copytree(EXAMPLES / "strong_task", root / "strong_task")
    names = tmp_path / "names.txt"
    names.write_text("strong_task\n\n")
    out = tmp_path / "o.csv"
    res = CliRunner().invoke(
        app, ["batch", str(root), "--static-only", "--only", str(names), "--csv", str(out), "--jobs", "2"]
    )
    assert res.exit_code == 0, res.output
    assert "scanned 1 tasks" in res.output and "strong_task: solid" in res.output


@pytest.mark.docker
def test_crlf_task_runs_in_real_container(tmp_path: Path) -> None:
    import shutil

    from verifierguard.fixer.verify_fix import run_oracle

    work = tmp_path / "crlf_task"
    shutil.copytree(EXAMPLES / "strong_task", work)
    for f in list(work.rglob("*.sh")):
        f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
    res = run_oracle(load_task(work), DockerRunner())
    assert res.passed, res
