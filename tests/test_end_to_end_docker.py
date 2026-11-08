"""Full scans through the CLI with real containers."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from conftest import EXAMPLES, FIXTURES
from verifierguard.cli import app

pytestmark = pytest.mark.docker
cli = CliRunner()


def test_weak_task_is_reported_weak_with_verified_tamper_fix(tmp_path) -> None:  # type: ignore[no-untyped-def]
    out = tmp_path / "weak.json"
    res = cli.invoke(app, ["scan", str(EXAMPLES / "weak_task"), "--expect", "weak", "--json", str(out)])
    assert res.exit_code == 0, res.output
    data = json.loads(out.read_text())
    assert data["verdict"] == "weak" and data["oracle_passed"] is True
    assert data["cheaters_passed"] == ["hard_code", "tamper"]
    by = {f["cheater"]: f for f in data["fixes"]}
    assert by["tamper"]["status"] == "verified"
    assert "reward.txt" in by["tamper"]["diff"]
    assert by["hard_code"]["status"] == "advice_only"
    assert "reset" not in (EXAMPLES / "weak_task" / "tests" / "test.sh").read_text()


def test_strong_task_is_solid() -> None:
    res = cli.invoke(app, ["scan", str(EXAMPLES / "strong_task"), "--expect", "solid"])
    assert res.exit_code == 0, res.output
    assert "SOLID" in res.output and "100/100" in res.output


def test_leaky_task_is_weak_via_peek() -> None:
    res = cli.invoke(app, ["scan", str(FIXTURES / "leaky_task"), "--expect", "weak", "--no-fix"])
    assert res.exit_code == 0, res.output
    assert "cheater test_peek" in res.output and "PASSED (gap) - visible to the agent" in res.output


def test_apply_writes_only_verified_fix(tmp_path) -> None:  # type: ignore[no-untyped-def]
    work = tmp_path / "weak_task"
    shutil.copytree(EXAMPLES / "weak_task", work)
    res = cli.invoke(app, ["scan", str(work), "--apply"])
    assert res.exit_code == 0, res.output
    assert "applied verified tamper fix" in res.output
    assert "VerifierGuard: reset reward" in (work / "tests" / "test.sh").read_text()
    # after applying, the tamper gap is gone
    again = cli.invoke(app, ["scan", str(work), "--no-fix"])
    assert "cheater tamper     blocked" in again.output


def test_without_apply_original_is_untouched(tmp_path) -> None:  # type: ignore[no-untyped-def]
    work = tmp_path / "weak_task"
    shutil.copytree(EXAMPLES / "weak_task", work)
    before = (work / "tests" / "test.sh").read_text()
    cli.invoke(app, ["scan", str(work)])
    assert (work / "tests" / "test.sh").read_text() == before
