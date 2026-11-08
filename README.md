# VerifierGuard

[![CI](https://github.com/Hem60/verifierguard/actions/workflows/ci.yml/badge.svg)](https://github.com/Hem60/verifierguard/actions/workflows/ci.yml)

**Tests the test.** An AI agent benchmark task has a *verifier* that decides pass or fail. If the
verifier is weak, an agent can pass by cheating (writing a fake answer, editing the reward file).
VerifierGuard plays the cheating student against your task, tells you which tricks worked, suggests a
fix, and **proves** the fix on a copy: the cheater must now fail and the correct solution must still pass.

It does not accuse any real agent. It tells the task author: *your verifier can be fooled, here is how,
and here is a tested fix.*

> Status: the core tool is built and tested (Docker based). It has **not** yet been run on a large set of
> public tasks, so there are no published results yet.

## Install

```bash
pip install -e ".[dev]"      # from a clone; needs Python 3.11+ and Docker for full scans
```

## Use

```bash
verifierguard scan ./my-task                 # full scan (needs Docker)
verifierguard scan ./my-task --static-only   # no Docker, pattern checks only
verifierguard scan ./my-task --json r.json --html r.html
verifierguard scan ./my-task --expect solid  # exit 1 unless the verdict matches (for CI)
verifierguard scan ./my-task --llm           # also ask Gemini for a fix (needs GEMINI_API_KEY)
verifierguard scan ./my-task --apply         # write VERIFIED fixes into the folder (off by default)
verifierguard batch ./tasks --csv results/scan.csv
```

A task is a Harbor style folder: `instruction.md`, `environment/Dockerfile`, `tests/test.sh`
(writes `/logs/verifier/reward.txt`), and optionally `solution/solve.sh` (the oracle).

## How it works

1. **Oracle check** - the correct solution must pass, otherwise the task is reported `broken`.
2. **Cheater agents**, each run in a fresh container followed by the real verifier:

   | Cheater | Does | If it passes |
   |---|---|---|
   | `do_nothing` | leaves everything untouched | verifier checks too little |
   | `hard_code` | writes made up values (`0`, `1`, `42`, `placeholder`) to the expected output files | verifier checks presence or a guessable value |
   | `test_peek` | searches for tests, answer key, `solve.sh` (and runs a found solution) | verifier material is visible to the agent |
   | `tamper` | pre-writes the reward file and overwrites test files | agent can change the reward and the verifier never resets it |

3. **Static checks** on `tests/` and the Dockerfile (codes `VG001`-`VG010`), e.g. reward written without
   a condition, failures swallowed with `|| true`, tests with no assertions, tests copied into the image.
4. **Score and verdict**: `solid`, `weak` (any cheater passed or a high severity finding) or `broken`.
5. **Fixes**
   - Level 1: rule based gap explanation and advice per cheater. The `tamper` gap has an automatic patch
     (reset the reward to `0` at the start of `test.sh`).
   - Level 2 (`--llm`): Gemini proposes a replacement `test.sh`.
   - Level 3: every patch is applied to a **copy**, the same cheater runs again (must fail) and the
     oracle runs again (must pass). Only then it is marked `verified` and shown as a diff. Otherwise the
     report says *fix suggested but not verified, please review by hand*.

The original task is never edited unless you pass `--apply`, and `--apply` only writes verified fixes.

## Limits

A clean scan means **no known gap, not no gap**. VerifierGuard only finds what its cheaters can reach.
Static checks are heuristics and can give false alarms: review findings before acting on them.
`hard_code` guesses output paths from the instruction and verifier text, so unusual layouts may be missed.

## Examples

`examples/weak_task` is breakable on purpose (the `hard_code` and `tamper` cheaters pass).
`examples/strong_task` is solid. CI scans both with `--expect weak` and `--expect solid`.

## Development

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && mypy src
pytest --cov=verifierguard        # Docker tests are skipped if no daemon is running
```

MIT licensed.
