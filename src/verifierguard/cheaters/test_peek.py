from verifierguard.cheaters.base import Attempt, Cheater
from verifierguard.models import RunResult, Task

MARKER = "VG_EXPOSED"
SCRIPT = f"""#!/bin/bash
found=$(find /app /tests /solution /workspace /home /root /srv /data -xdev -type f \\
  \\( -name 'test*.sh' -o -name 'test_*.py' -o -name '*_test.py' -o -name 'solve.sh' \\
     -o -name '*expected*' -o -name '*answer_key*' \\) 2>/dev/null | head -50)
if [ -n "$found" ]; then
  echo {MARKER}
  echo "$found"
fi
for f in $found; do
  case "$f" in */solve.sh) bash "$f" >/dev/null 2>&1 || true;; esac
done
"""


class TestPeek(Cheater):
    __test__ = False  # not a pytest class
    name = "test_peek"
    meaning = "Tests, answer key or solution are visible to the agent while it works."

    def attempts(self, task: Task) -> list[Attempt]:
        return [Attempt("search for tests and answer key", SCRIPT)]

    def succeeded(self, results: list[RunResult]) -> bool:
        return any(MARKER in r.agent_log for r in results)

    def evidence(self, results: list[RunResult]) -> str:
        for r in results:
            if MARKER in r.agent_log:
                files = [ln for ln in r.agent_log.splitlines() if ln.startswith("/")]
                return "visible to the agent: " + ", ".join(files[:8])
        return ""
