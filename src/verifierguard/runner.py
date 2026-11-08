"""Run an agent script and then the verifier inside a Docker container."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Protocol

from verifierguard.models import RunResult, Task

AGENT_TIMEOUT = 120
VERIFIER_TIMEOUT = 300
BUILD_TIMEOUT = 900
SHORT = 60


class RunnerError(Exception):
    """Docker is missing, down, or the image failed to build."""


class Runner(Protocol):
    def run(self, task: Task, script: str, label: str, with_solution: bool = False) -> RunResult: ...


def docker_available(docker: str = "docker") -> bool:
    if shutil.which(docker) is None:
        return False
    try:
        out = subprocess.run(
            [docker, "info", "--format", "{{.ServerVersion}}"], capture_output=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def _tail(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else "...[truncated]...\n" + text[-limit:]


def parse_reward(raw: str) -> float | None:
    """Accept '1', '0.5' or a small json object holding a reward value."""
    text = raw.strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict) and data:
        value = data.get("reward", next(iter(data.values())))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


class DockerRunner:
    """One fresh container per run, so cheaters cannot affect each other."""

    def __init__(self, docker: str = "docker", memory: str = "1g", cpus: str = "1") -> None:
        self.docker = docker
        self.memory = memory
        self.cpus = cpus
        self._images: dict[Path, str] = {}

    def _cmd(self, *args: str, timeout: int, check: bool = False) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(
                [self.docker, *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RunnerError(f"docker {args[0]} timed out after {timeout}s") from exc
        except OSError as exc:
            raise RunnerError(f"cannot run docker: {exc}") from exc
        if check and proc.returncode != 0:
            raise RunnerError(f"docker {args[0]} failed: {_tail(proc.stderr or proc.stdout)}")
        return proc

    def build(self, task: Task) -> str:
        cached = self._images.get(task.path)
        if cached:
            return cached
        digest = hashlib.sha256(str(task.path).encode()).hexdigest()[:10]
        safe = "".join(c if c.isalnum() else "-" for c in task.name.lower()).strip("-") or "task"
        tag = f"vg-{safe}-{digest}"
        self._cmd("build", "-q", "-t", tag, str(task.env_dir), timeout=BUILD_TIMEOUT, check=True)
        self._images[task.path] = tag
        return tag

    def run(self, task: Task, script: str, label: str, with_solution: bool = False) -> RunResult:
        result = RunResult(label=label)
        image = self.build(task)
        name = f"vg-{uuid.uuid4().hex[:12]}"
        self._cmd(
            "run", "-d", "--name", name, "--memory", self.memory, "--cpus", self.cpus,
            "--pids-limit", "512", image, "sleep", "infinity",
            timeout=120, check=True,
        )  # fmt: skip
        try:
            self._cmd("exec", name, "mkdir", "-p", "/logs/agent", "/logs/verifier",
                      timeout=SHORT, check=True)  # fmt: skip
            with tempfile.TemporaryDirectory(prefix="vg_") as tmp:
                script_file = Path(tmp) / "vg_agent.sh"
                script_file.write_bytes(script.replace("\r\n", "\n").encode("utf-8"))
                self._cmd("cp", str(script_file), f"{name}:/tmp/vg_agent.sh",
                          timeout=SHORT, check=True)  # fmt: skip
            if with_solution:
                self._cmd("exec", name, "mkdir", "-p", "/solution", timeout=SHORT, check=True)
                self._cmd("cp", f"{task.solution_dir}/.", f"{name}:/solution/",
                          timeout=SHORT, check=True)  # fmt: skip

            try:
                agent = self._cmd("exec", name, "bash", "/tmp/vg_agent.sh", timeout=AGENT_TIMEOUT)
                result.agent_exit = agent.returncode
                result.agent_log = _tail(agent.stdout + agent.stderr)

                self._cmd("exec", name, "mkdir", "-p", "/tests", timeout=SHORT, check=True)
                self._cmd("cp", f"{task.tests_dir}/.", f"{name}:/tests/",
                          timeout=SHORT, check=True)  # fmt: skip
                ver = self._cmd("exec", name, "bash", "/tests/test.sh", timeout=VERIFIER_TIMEOUT)
                result.verifier_log = _tail(ver.stdout + ver.stderr)
            except RunnerError as exc:
                result.error = str(exc)
                return result
            result.reward = self._read_reward(name)
        finally:
            self._cmd("rm", "-f", name, timeout=SHORT)
        return result

    def _read_reward(self, name: str) -> float | None:
        for filename in ("reward.txt", "reward.json"):
            out = self._cmd("exec", name, "cat", f"/logs/verifier/{filename}", timeout=SHORT)
            if out.returncode == 0:
                return parse_reward(out.stdout)
        return None
