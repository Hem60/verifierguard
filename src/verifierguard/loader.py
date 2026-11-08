"""Read a Harbor task folder."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from verifierguard.models import Task

REQUIRED = ("instruction.md", "environment/Dockerfile", "tests/test.sh")
_WORKDIR_RE = re.compile(r"^\s*WORKDIR\s+(\S+)", re.MULTILINE | re.IGNORECASE)
_TEXT_SUFFIXES = {".sh", ".py", ".txt", ".json", ".toml", ""}


class TaskError(Exception):
    """The folder is not a usable task."""


def load_task(path: str | Path) -> Task:
    root = Path(path).resolve()
    if not root.is_dir():
        raise TaskError(f"not a directory: {root}")
    missing = [rel for rel in REQUIRED if not (root / rel).is_file()]
    if missing:
        raise TaskError(f"{root.name}: missing required files: {', '.join(missing)}")

    config: dict[str, object] = {}
    toml_path = root / "task.toml"
    if toml_path.is_file():
        try:
            config = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise TaskError(f"{root.name}: bad task.toml: {exc}") from exc

    dockerfile = (root / "environment" / "Dockerfile").read_text(encoding="utf-8")
    matches = _WORKDIR_RE.findall(dockerfile)
    workdir = matches[-1] if matches else "/app"

    verifier_files: dict[str, str] = {}
    tests_dir = root / "tests"
    for file in sorted(tests_dir.rglob("*")):
        if file.is_file() and file.suffix in _TEXT_SUFFIXES:
            rel = file.relative_to(tests_dir).as_posix()
            verifier_files[rel] = file.read_text(encoding="utf-8", errors="replace")

    return Task(
        path=root,
        name=root.name,
        instruction=(root / "instruction.md").read_text(encoding="utf-8"),
        dockerfile=dockerfile,
        workdir=workdir,
        verifier_files=verifier_files,
        has_solution=(root / "solution" / "solve.sh").is_file(),
        config=config,
    )


_ABS_PATH_RE = re.compile(r"(?<![\w/.])(/(?:[\w.-]+/)*[\w.-]+\.\w{1,6})\b")
_REL_FILE_RE = re.compile(r"(?<![\w/.])([\w-]+\.(?:txt|json|csv|md|out|log|yaml|yml|py))\b")
_IGNORED_PREFIXES = ("/tests", "/logs", "/solution", "/usr", "/etc", "/bin", "/proc", "/tmp")
_IGNORED_NAMES = {"instruction.md", "task.toml", "reward.txt", "reward.json"}


def candidate_output_paths(task: Task) -> list[str]:
    """Files the task seems to ask the agent to produce (best effort, max 6)."""
    text = task.instruction + "\n" + task.verifier_text
    found: list[str] = []
    for path in _ABS_PATH_RE.findall(text):
        if not path.startswith(_IGNORED_PREFIXES) and path not in found:
            found.append(path)
    for name in _REL_FILE_RE.findall(text):
        if name in _IGNORED_NAMES or name.startswith("test_"):
            continue
        full = f"{task.workdir.rstrip('/')}/{name}"
        if full not in found:
            found.append(full)
    return found[:6]
