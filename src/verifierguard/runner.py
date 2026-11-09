"""Run an agent script and then the verifier inside a Docker container."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Protocol

from verifierguard.models import RunResult, Task

CHEATER_TIMEOUT = 120
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


INFRA_MARKERS = (
    "failed to download",
    "could not resolve host",
    "temporary failure in name resolution",
    "unable to locate package",
    "uvx: command not found",
    "uv: command not found",
    "network is unreachable",
    "connection timed out",
    "connection reset",
    "connection refused",
    "returned error: 5",
    "curl: (6)",
    "curl: (7)",
    "curl: (22)",
    "curl: (28)",
    "curl: (35)",
    "curl: (56)",
)
RETRIES = 3


def looks_like_infra_failure(result: RunResult) -> bool:
    """The verifier gave no credit AND its log shows a network or tooling failure."""
    if result.passed:
        return False
    if result.error:
        return True
    log = result.verifier_log.lower()
    return any(marker in log for marker in INFRA_MARKERS)


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


CRLF = bytes([13, 10])
LF = bytes([10])


def stage_dir(src: Path, dest: Path) -> Path:
    """Copy a tests/solution folder, turning CRLF into LF in shell scripts.

    Task folders checked out on Windows often have CRLF, which breaks bash inside Linux.
    """
    shutil.copytree(src, dest)
    for script in dest.rglob("*.sh"):
        data = script.read_bytes()
        if CRLF in data:
            script.write_bytes(data.replace(CRLF, LF))
    return dest


class DockerRunner:
    """One fresh container per run, so cheaters cannot affect each other."""

    def __init__(
        self,
        docker: str = "docker",
        memory: str = "1g",
        cpus: str = "1",
        prebuilt: bool = False,
    ) -> None:
        self.docker = docker
        self.memory = memory
        self.cpus = cpus
        self.prebuilt = prebuilt
        self._images: dict[Path, str] = {}
        self._pulled: dict[Path, bool] = {}
        self._lock = threading.Lock()

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
        with self._lock:
            return self._build_locked(task)

    def _build_locked(self, task: Task) -> str:
        cached = self._images.get(task.path)
        if cached:
            return cached
        if self.prebuilt and task.docker_image:
            pull = self._cmd("pull", "-q", task.docker_image, timeout=BUILD_TIMEOUT)
            if pull.returncode == 0:
                self._images[task.path] = task.docker_image
                self._pulled[task.path] = True
                return task.docker_image
        digest = hashlib.sha256(str(task.path).encode()).hexdigest()[:10]
        safe = "".join(c if c.isalnum() else "-" for c in task.name.lower()).strip("-") or "task"
        tag = f"vg-{safe}-{digest}"
        self._cmd("build", "-q", "-t", tag, str(task.env_dir), timeout=BUILD_TIMEOUT, check=True)
        self._images[task.path] = tag
        return tag

    def run(self, task: Task, script: str, label: str, with_solution: bool = False) -> RunResult:
        """Run once; retry when the verifier failed for infrastructure reasons, not task reasons."""
        result = self._run_once(task, script, label, with_solution)
        for attempt in range(1, RETRIES):
            if not looks_like_infra_failure(result):
                return result
            time.sleep(10 * attempt)
            result = self._run_once(task, script, label, with_solution)
        result.infra_failure = looks_like_infra_failure(result)
        return result

    def _run_once(self, task: Task, script: str, label: str, with_solution: bool = False) -> RunResult:
        result = RunResult(label=label)
        image = self.build(task)
        name = f"vg-{uuid.uuid4().hex[:12]}"
        self._cmd(
            "run", "-d", "--name", name, "--memory", task.memory or self.memory, "--cpus", self.cpus,
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
                with tempfile.TemporaryDirectory(prefix="vg_sol_") as sol_tmp:
                    staged = stage_dir(task.solution_dir, Path(sol_tmp) / "solution")
                    self._cmd("exec", name, "mkdir", "-p", "/solution", timeout=SHORT, check=True)
                    self._cmd("cp", f"{staged}/.", f"{name}:/solution/",
                              timeout=SHORT, check=True)  # fmt: skip

            try:
                agent_limit = task.agent_timeout if with_solution else CHEATER_TIMEOUT
                agent = self._cmd("exec", name, "bash", "/tmp/vg_agent.sh", timeout=agent_limit)
                result.agent_exit = agent.returncode
                result.agent_log = _tail(agent.stdout + agent.stderr)

                self._cmd("exec", name, "mkdir", "-p", "/tests", timeout=SHORT, check=True)
                with tempfile.TemporaryDirectory(prefix="vg_tests_") as tests_tmp:
                    staged_tests = stage_dir(task.tests_dir, Path(tests_tmp) / "tests")
                    self._cmd("cp", f"{staged_tests}/.", f"{name}:/tests/",
                              timeout=SHORT, check=True)  # fmt: skip
                ver = self._cmd("exec", name, "bash", "/tests/test.sh", timeout=task.verifier_timeout)
                result.verifier_log = _tail(ver.stdout + ver.stderr)
            except RunnerError as exc:
                result.error = str(exc)
                return result
            result.reward = self._read_reward(name)
        finally:
            self._cmd("rm", "-f", name, timeout=SHORT)
        return result

    def cleanup(self, task: Task) -> None:
        """Remove the image of this task (only if we pulled or built it), to save disk."""
        with self._lock:
            tag = self._images.pop(task.path, None)
            self._pulled.pop(task.path, None)
        if tag:
            self._cmd("rmi", "-f", tag, timeout=SHORT)

    def _read_reward(self, name: str) -> float | None:
        for filename in ("reward.txt", "reward.json"):
            out = self._cmd("exec", name, "cat", f"/logs/verifier/{filename}", timeout=SHORT)
            if out.returncode == 0:
                return parse_reward(out.stdout)
        return None
