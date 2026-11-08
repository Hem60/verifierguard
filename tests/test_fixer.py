import pytest

from conftest import FakeRunner
from verifierguard.cheaters.base import CheaterResult
from verifierguard.fixer.llm_fix import extract_script, gemini_call, propose_fix
from verifierguard.fixer.rules import RESET_MARK, Fix, reset_reward, suggest_fixes
from verifierguard.fixer.verify_fix import ADVICE_ONLY, NOT_VERIFIED, VERIFIED, prove_fix
from verifierguard.loader import load_task
from verifierguard.static_checks import Finding


def result(name: str, ok: bool = True) -> CheaterResult:
    return CheaterResult(name=name, succeeded=ok, meaning="m", evidence="e")


def test_reset_reward_is_idempotent(make_task) -> None:  # type: ignore[no-untyped-def]
    root = make_task(test_sh="#!/bin/bash\necho 1 > /logs/verifier/reward.txt\n")
    reset_reward(root)
    once = (root / "tests" / "test.sh").read_text()
    reset_reward(root)
    assert (root / "tests" / "test.sh").read_text() == once
    assert once.startswith("#!/bin/bash\n# VerifierGuard") and RESET_MARK in once


def test_reset_reward_without_shebang(make_task) -> None:  # type: ignore[no-untyped-def]
    root = make_task(test_sh="echo hi\n")
    reset_reward(root)
    assert (root / "tests" / "test.sh").read_text().startswith(RESET_MARK)


def test_suggest_fixes_maps_each_cheater() -> None:
    fixes = suggest_fixes([result(n) for n in ("do_nothing", "hard_code", "test_peek", "tamper")], [])
    by = {f.cheater: f for f in fixes}
    assert set(by) == {"do_nothing", "hard_code", "test_peek", "tamper"}
    assert by["tamper"].patch is reset_reward
    assert by["hard_code"].patch is None
    assert suggest_fixes([result("tamper", False)], []) == []


def test_static_findings_add_fixes_without_duplicates() -> None:
    f5 = Finding("VG005", "medium", "no reset", "d")
    f10 = Finding("VG010", "high", "copied", "d")
    fixes = suggest_fixes([], [f5, f10])
    assert {f.cheater for f in fixes} == {"tamper", "test_peek"}
    assert len(suggest_fixes([result("tamper")], [f5])) == 1


def good_oracle_runner(cheat_passes_unless_marker: bool):  # type: ignore[no-untyped-def]
    """Cheater only passes when tests/test.sh has no reset marker."""

    def decide(task, script, label, with_solution):  # type: ignore[no-untyped-def]
        if with_solution:
            return 1.0, ""
        patched = RESET_MARK in task.verifier_files["test.sh"]
        return (0.0 if patched and cheat_passes_unless_marker else 1.0), ""

    return FakeRunner(decide)


def test_prove_fix_verified(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    fix = Fix("tamper", "g", "s", reset_reward)
    proof = prove_fix(task, fix, good_oracle_runner(True))
    assert proof.status == VERIFIED and proof.verified
    assert "+echo 0 > /logs/verifier/reward.txt" in proof.diff
    # the original must be untouched
    assert RESET_MARK not in (task.path / "tests" / "test.sh").read_text()


def test_prove_fix_cheater_still_passes(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    proof = prove_fix(task, Fix("tamper", "g", "s", reset_reward), good_oracle_runner(False))
    assert proof.status == NOT_VERIFIED
    assert "still passes" in proof.reason and "not verified" in proof.reason


def test_prove_fix_breaks_oracle(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    runner = FakeRunner(lambda t, s, label, with_sol: (0.0, ""))
    proof = prove_fix(task, Fix("tamper", "g", "s", reset_reward), runner)
    assert proof.status == NOT_VERIFIED and "no longer passes" in proof.reason


def test_prove_fix_advice_only_and_missing_solution(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    assert prove_fix(task, Fix("hard_code", "g", "s"), FakeRunner(lambda *_: (0, ""))).status == ADVICE_ONLY
    nosol = load_task(make_task(solution=False))
    proof = prove_fix(nosol, Fix("tamper", "g", "s", reset_reward), FakeRunner(lambda *_: (0, "")))
    assert proof.status == NOT_VERIFIED and "solution" in proof.reason


def test_prove_fix_unknown_cheater(make_task) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    proof = prove_fix(task, Fix("nope", "g", "s", reset_reward), FakeRunner(lambda *_: (0, "")))
    assert proof.status == NOT_VERIFIED and "unknown cheater" in proof.reason


LLM_SCRIPT = "#!/bin/bash\necho 0 > /logs/verifier/reward.txt\n"


def test_extract_script() -> None:
    assert extract_script(f"```bash\n{LLM_SCRIPT}```") == LLM_SCRIPT
    assert extract_script(LLM_SCRIPT) == LLM_SCRIPT
    assert extract_script("sorry, I cannot") is None
    assert extract_script("```bash\n#!/bin/bash\necho hi\n```") is None  # no reward


def test_propose_fix_patches_a_copy(make_task, tmp_path) -> None:  # type: ignore[no-untyped-def]
    task = load_task(make_task())
    seen: list[str] = []

    def fake(prompt: str) -> str:
        seen.append(prompt)
        return f"```bash\n{LLM_SCRIPT}```"

    fix = propose_fix(task, result("hard_code"), fake)
    assert fix is not None and fix.source == "llm" and fix.patch is not None
    assert "hard_code" in seen[0] and "reward.txt" in seen[0]
    fix.patch(task.path)
    assert (task.path / "tests" / "test.sh").read_text() == LLM_SCRIPT
    assert propose_fix(task, result("hard_code"), lambda _p: "no idea") is None


def test_gemini_call_needs_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        gemini_call("hi")


def test_gemini_call_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import json
    import urllib.request

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    payload = {"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}
    sent = {}

    def fake_urlopen(req, timeout):  # type: ignore[no-untyped-def]
        sent["key"] = req.get_header("X-goog-api-key")
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert gemini_call("hi") == "hello"
    assert sent["key"] == "test-key"

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: io.BytesIO(b"{}"))
    with pytest.raises(RuntimeError, match="unexpected"):
        gemini_call("hi")
