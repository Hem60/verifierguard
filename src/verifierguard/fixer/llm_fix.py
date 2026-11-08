"""Level 2: ask a free LLM (Gemini) for a task specific verifier fix.

The answer is only a proposal. It must pass `prove_fix` before it is called verified.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

from verifierguard.cheaters.base import CheaterResult
from verifierguard.fixer.rules import Fix
from verifierguard.models import Task

MODEL = "gemini-2.5-flash"
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

Caller = Callable[[str], str]

PROMPT = """You review the verifier of an AI agent benchmark task (Harbor format).
The verifier is /tests/test.sh. It must write 1 (pass) or 0 (fail) to /logs/verifier/reward.txt.

A cheating agent passed this verifier without doing the task.
Cheater: {cheater} ({meaning})
Evidence: {evidence}

Task instruction:
{instruction}

Current tests/test.sh:
```bash
{test_sh}
```

Rewrite tests/test.sh so the cheater fails but a correct solution still passes.
Reset the reward to 0 first. Reply with ONE complete bash script in a ```bash block and nothing else."""


def gemini_call(prompt: str) -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - fixed https URL
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc
    try:
        return str(data["candidates"][0]["content"]["parts"][0]["text"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("unexpected Gemini response shape") from exc


_BLOCK = re.compile(r"```(?:bash|sh)?\s*\n(.*?)```", re.DOTALL)


def extract_script(answer: str) -> str | None:
    match = _BLOCK.search(answer)
    script = (match.group(1) if match else answer).strip()
    if not script.startswith("#!") or "reward" not in script:
        return None
    return script + "\n"


def propose_fix(task: Task, result: CheaterResult, call: Caller = gemini_call) -> Fix | None:
    prompt = PROMPT.format(
        cheater=result.name,
        meaning=result.meaning,
        evidence=result.evidence or "(none)",
        instruction=task.instruction.strip(),
        test_sh=task.verifier_files.get("test.sh", ""),
    )
    script = extract_script(call(prompt))
    if script is None:
        return None

    def patch(root: Path) -> None:
        (root / "tests" / "test.sh").write_text(script, encoding="utf-8", newline="\n")

    return Fix(
        cheater=result.name,
        gap=result.meaning,
        suggestion="LLM written replacement for tests/test.sh (must be proven before use).",
        patch=patch,
        source="llm",
    )
