import csv
import json

import pytest
from typer.testing import CliRunner

from conftest import EXAMPLES, FakeRunner
from verifierguard.batch import find_tasks, run_batch
from verifierguard.cli import app
from verifierguard.loader import load_task
from verifierguard.report import render_html, render_text, to_json
from verifierguard.scanner import BROKEN, SOLID, WEAK, compute_score, scan_task

cli = CliRunner()


def test_static_only_scan_has_no_cheaters(make_task) -> None:  # type: ignore[no-untyped-def]
    report = scan_task(load_task(make_task()), None)
    assert not report.dynamic and report.cheaters == [] and report.verdict == WEAK


def test_fake_runner_solid(make_task) -> None:  # type: ignore[no-untyped-def]
    sh = (
        "#!/bin/bash\necho 0 > /logs/verifier/reward.txt\n"
        "if grep -q 1 /app/a; then echo 1 > /logs/verifier/reward.txt; fi\n"
    )
    runner = FakeRunner(lambda t, s, label, sol: (1.0 if sol else 0.0, ""))
    report = scan_task(load_task(make_task(test_sh=sh)), runner)
    assert report.verdict == SOLID and report.score == 100 and report.oracle_passed


def test_broken_when_oracle_fails(make_task) -> None:  # type: ignore[no-untyped-def]
    runner = FakeRunner(lambda *_: (0.0, ""))
    report = scan_task(load_task(make_task()), runner)
    assert report.verdict == BROKEN and report.cheaters == []


def test_weak_with_fixes_and_llm(make_task) -> None:  # type: ignore[no-untyped-def]
    runner = FakeRunner(lambda *_: (1.0, "VG_EXPOSED\n/app/solve.sh\n"))
    seen = []

    def llm(prompt: str) -> str:
        seen.append(prompt)
        return "```bash\n#!/bin/bash\necho 0 > /logs/verifier/reward.txt\n```"

    report = scan_task(load_task(make_task()), runner, use_llm=True, llm_call=llm)
    assert report.verdict == WEAK and report.score == 0
    sources = {f.fix.source for f in report.fixes}
    assert sources == {"rule", "llm"} and seen
    data = report.to_dict()
    assert data["cheaters_passed"] == ["do_nothing", "hard_code", "test_peek", "tamper"]


def test_llm_failure_is_not_fatal(make_task) -> None:  # type: ignore[no-untyped-def]
    runner = FakeRunner(lambda *_: (1.0, ""))

    def boom(_p: str) -> str:
        raise RuntimeError("offline")

    report = scan_task(load_task(make_task()), runner, use_llm=True, llm_call=boom)
    assert all(f.fix.source == "rule" for f in report.fixes)


def test_compute_score_floor() -> None:
    assert compute_score([], []) == 100


def test_reports_render(make_task) -> None:  # type: ignore[no-untyped-def]
    runner = FakeRunner(lambda t, s, label, sol: (1.0, ""))
    report = scan_task(
        load_task(make_task(test_sh="#!/bin/bash\necho 1 > /logs/verifier/reward.txt\n<x>\n")), runner
    )
    html = render_html(report)
    assert html.startswith("<!doctype html>") and "WEAK" in html
    assert json.loads(to_json(report))["verdict"] == "weak"
    text = render_text(report)
    assert "Verdict: WEAK" in text and "no known gap" in text
    static = render_text(scan_task(load_task(make_task()), None))
    assert "static checks only" in static
    assert "Static checks only" in render_html(scan_task(load_task(make_task()), None))


def test_cli_version() -> None:
    assert cli.invoke(app, ["version"]).exit_code == 0


def test_cli_static_scan_expect(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ok = cli.invoke(app, ["scan", str(EXAMPLES / "strong_task"), "--static-only", "--expect", "solid"])
    assert ok.exit_code == 0, ok.output
    bad = cli.invoke(app, ["scan", str(EXAMPLES / "strong_task"), "--static-only", "--expect", "weak"])
    assert bad.exit_code == 1
    out = tmp_path / "r.json"
    html = tmp_path / "r.html"
    res = cli.invoke(
        app, ["scan", str(EXAMPLES / "weak_task"), "--static-only", "--json", str(out), "--html", str(html)]
    )
    assert res.exit_code == 0 and json.loads(out.read_text())["task"] == "weak_task"
    assert html.read_text().startswith("<!doctype html>")


def test_cli_errors(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert cli.invoke(app, ["scan", str(tmp_path / "missing"), "--static-only"]).exit_code == 2
    assert cli.invoke(app, ["batch", str(tmp_path / "missing")]).exit_code == 2


def test_cli_without_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("verifierguard.cli.docker_available", lambda: False)
    res = cli.invoke(app, ["scan", str(EXAMPLES / "weak_task")])
    assert res.exit_code == 2 and "Docker is not available" in res.output


def test_batch_static(tmp_path) -> None:  # type: ignore[no-untyped-def]
    broken = tmp_path / "tasks" / "broken"
    broken.mkdir(parents=True)
    import shutil

    shutil.copytree(EXAMPLES / "weak_task", tmp_path / "tasks" / "weak_task")
    shutil.copytree(EXAMPLES / "strong_task", tmp_path / "tasks" / "strong_task")
    assert [p.name for p in find_tasks(tmp_path / "tasks")] == ["strong_task", "weak_task"]
    out = tmp_path / "out" / "scan.csv"
    assert run_batch(tmp_path / "tasks", out, None) == 2
    rows = {r["task"]: r for r in csv.DictReader(out.open())}
    assert rows["strong_task"]["verdict"] == "solid"
    assert rows["weak_task"]["static_findings"] == "VG005;VG006"
    res = cli.invoke(app, ["batch", str(tmp_path / "tasks"), "--static-only", "--csv", str(out)])
    assert res.exit_code == 0 and "scanned 2 tasks" in res.output


def test_batch_error_row(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import shutil

    root = tmp_path / "tasks"
    shutil.copytree(EXAMPLES / "weak_task", root / "bad")
    (root / "bad" / "task.toml").write_text("= = broken")
    out = tmp_path / "scan.csv"
    run_batch(root, out, None)
    row = next(csv.DictReader(out.open()))
    assert "task error" in row["error"]
