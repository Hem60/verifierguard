"""Command line entry."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from verifierguard import __version__
from verifierguard.batch import run_batch
from verifierguard.loader import TaskError, load_task
from verifierguard.report import render_text, write_html, write_json
from verifierguard.runner import DockerRunner, RunnerError, docker_available
from verifierguard.scanner import SOLID, WEAK, ScanReport, scan_task

app = typer.Typer(help="Check whether an AI agent benchmark task can be cheated.", no_args_is_help=True)


class Expect(StrEnum):
    weak = "weak"
    solid = "solid"


@app.callback()
def main() -> None:
    """VerifierGuard command line."""


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)


def _runner(static_only: bool) -> DockerRunner | None:
    if static_only:
        return None
    if not docker_available():
        typer.echo("error: Docker is not available. Start Docker or use --static-only.", err=True)
        raise typer.Exit(2)
    return DockerRunner()


def _apply(report: ScanReport, task_path: Path) -> None:
    """Write verified patches into the original folder. Only runs when --apply is given."""
    for outcome in report.fixes:
        if outcome.proof.verified and outcome.fix.patch is not None:
            outcome.fix.patch(task_path)
            typer.echo(f"applied verified {outcome.fix.cheater} fix to {task_path}")


@app.command()
def scan(
    task_dir: Annotated[Path, typer.Argument(help="Path to a Harbor task folder.")],
    expect: Annotated[Expect | None, typer.Option(help="Exit 1 unless the verdict matches.")] = None,
    json_out: Annotated[Path | None, typer.Option("--json", help="Write a JSON report.")] = None,
    html_out: Annotated[Path | None, typer.Option("--html", help="Write an HTML report.")] = None,
    static_only: Annotated[bool, typer.Option(help="Skip Docker, run static checks only.")] = False,
    fix: Annotated[bool, typer.Option("--fix/--no-fix", help="Suggest and prove fixes.")] = True,
    llm: Annotated[bool, typer.Option(help="Also ask Gemini (GEMINI_API_KEY) for fixes.")] = False,
    apply: Annotated[bool, typer.Option(help="Write VERIFIED fixes into the task folder.")] = False,
) -> None:
    """Attack a task's verifier with cheater agents and report the gaps."""
    try:
        task = load_task(task_dir)
        report = scan_task(task, _runner(static_only), propose_fixes=fix, use_llm=llm)
    except TaskError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    except RunnerError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc

    typer.echo(render_text(report))
    if json_out:
        write_json(report, json_out)
    if html_out:
        write_html(report, html_out)
    if apply:
        _apply(report, task.path)

    if expect is not None:
        wanted = WEAK if expect is Expect.weak else SOLID
        if report.verdict != wanted:
            typer.echo(f"expected {wanted} but got {report.verdict}", err=True)
            raise typer.Exit(1)


@app.command()
def batch(
    tasks_dir: Annotated[Path, typer.Argument(help="Folder holding many task folders.")],
    csv_out: Annotated[Path, typer.Option("--csv", help="CSV file to write.")] = Path("results/scan.csv"),
    static_only: Annotated[bool, typer.Option(help="Skip Docker, run static checks only.")] = False,
) -> None:
    """Scan every task folder inside TASKS_DIR and save one CSV row each."""
    if not tasks_dir.is_dir():
        typer.echo(f"error: not a directory: {tasks_dir}", err=True)
        raise typer.Exit(2)
    count = run_batch(tasks_dir, csv_out, _runner(static_only))
    typer.echo(f"scanned {count} tasks -> {csv_out}")
