"""Command line entry."""

import typer

from verifierguard import __version__

app = typer.Typer(help="Check whether an AI agent benchmark task can be cheated.")


@app.callback()
def main() -> None:
    """VerifierGuard command line."""


@app.command()
def version() -> None:
    """Print the installed version."""
    typer.echo(__version__)
