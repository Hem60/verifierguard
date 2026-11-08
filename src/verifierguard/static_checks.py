"""Scan the verifier (and Dockerfile) for weak patterns, without running anything."""

from __future__ import annotations

import re
from dataclasses import dataclass

from verifierguard.models import Task

HIGH, MEDIUM, LOW = "high", "medium", "low"
PENALTY = {HIGH: 15, MEDIUM: 8, LOW: 3}

_REWARD_WRITE = re.compile(r"""echo\s+['"]?(\S+?)['"]?\s*>+\s*\S*reward\.(?:txt|json)""")
_REWARD_JSON = re.compile(r"reward\.json")
_CONTENT_CHECK = re.compile(
    r"\b(grep|diff|cmp|awk|sed|python3?|pytest|jq|sha\d*sum|md5sum)\b|==|\[\s+\S+\s+=\s"
)
_EXISTENCE_ONLY = re.compile(r"\[\s+-[fesd]\s|\btest\s+-[fesd]\s|os\.path\.(exists|isfile)|\.exists\(\)")
_CONDITIONAL = re.compile(r"\b(if|elif|case)\b|&&|\|\|")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    title: str
    detail: str
    file: str = ""


def _code_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _check_shell(name: str, text: str) -> list[Finding]:
    lines = _code_lines(text)
    code = "\n".join(lines)
    out: list[Finding] = []

    writes = _REWARD_WRITE.findall(code)
    if not writes and not _REWARD_JSON.search(code) and "reward" not in code:
        out.append(Finding("VG001", HIGH, "Verifier never writes a reward",
                           "No write to a reward file was found, so the result depends on whatever "
                           "already exists.", name))  # fmt: skip
    if writes and not _CONDITIONAL.search(code):
        out.append(Finding("VG002", HIGH, "Reward is written without any condition",
                           "The verifier writes a reward with no if/&&/|| around it, so it always "
                           "gives credit.", name))  # fmt: skip
    if re.search(r"^\s*exit\s+0\s*$", code, re.MULTILINE) and not _CONDITIONAL.search(code):
        out.append(Finding("VG003", HIGH, "Verifier exits 0 unconditionally",
                           "A bare 'exit 0' means failures cannot be reported.", name))  # fmt: skip
    if re.search(r"(pytest|python3?\s+\S+)[^\n]*\|\|\s*(true|:)", code):
        out.append(Finding("VG004", HIGH, "Test failures are swallowed",
                           "'|| true' after the test command hides failures.", name))  # fmt: skip

    pass_values = {w for w in writes}
    resets = any(w in {"0", "0.0"} for w in pass_values) or "rm -f" in code and "reward" in code
    if writes and not resets:
        out.append(Finding("VG005", MEDIUM, "Reward file is not reset to a failing value first",
                           "The verifier only ever writes a passing reward. A reward file left by "
                           "the agent survives.", name))  # fmt: skip

    if _EXISTENCE_ONLY.search(code) and not _CONTENT_CHECK.search(code) and _CONDITIONAL.search(code):
        out.append(Finding("VG006", MEDIUM, "Only checks that a file exists",
                           "No content comparison was found next to the existence check.", name))  # fmt: skip
    return out


def _check_python(name: str, text: str) -> list[Finding]:
    asserts = len(re.findall(r"^\s*assert\b", text, re.MULTILINE))
    raises = len(re.findall(r"pytest\.raises|self\.assert\w+", text))
    if asserts + raises == 0:
        return [Finding("VG007", HIGH, "Test file has no assertions",
                        "Nothing in this file can fail, so it proves nothing.", name)]  # fmt: skip
    if re.search(r"^\s*def test_\w+\([^)]*\):\s*\n\s+pass\b", text, re.MULTILINE):
        return [Finding("VG008", MEDIUM, "Empty test function",
                        "A test body that is just 'pass' always succeeds.", name)]  # fmt: skip
    return []


def _check_dockerfile(task: Task) -> list[Finding]:
    out = []
    for line in task.dockerfile.splitlines():
        stripped = line.strip()
        if re.match(r"(COPY|ADD)\s", stripped, re.IGNORECASE) and re.search(
            r"\b(tests?|solutions?|solve\.sh|test\.sh|expected\S*|answer_key\S*)\b", stripped
        ):
            out.append(Finding("VG010", HIGH, "Tests or solution are copied into the image",
                               f"'{stripped}' puts verifier material where the agent can read it.",
                               "environment/Dockerfile"))  # fmt: skip
    return out


def run_static_checks(task: Task) -> list[Finding]:
    findings: list[Finding] = []
    for name, text in task.verifier_files.items():
        if name.endswith(".sh"):
            findings += _check_shell(name, text)
        elif name.endswith(".py") and name != "__init__.py":
            findings += _check_python(name, text)
    findings += _check_dockerfile(task)
    return findings
