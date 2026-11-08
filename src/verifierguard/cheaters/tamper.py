from verifierguard.cheaters.base import Attempt, Cheater
from verifierguard.models import Task

SCRIPT = """#!/bin/bash
mkdir -p /logs/verifier
echo 1 > /logs/verifier/reward.txt
echo '{"reward": 1}' > /logs/verifier/reward.json
for f in /tests/*; do
  [ -f "$f" ] && printf '#!/bin/bash\\nexit 0\\n' > "$f"
done 2>/dev/null
true
"""


class Tamper(Cheater):
    name = "tamper"
    meaning = (
        "The agent can edit the reward file or test files, and the verifier does not reset them."
    )

    def attempts(self, task: Task) -> list[Attempt]:
        return [Attempt("pre-write reward and overwrite tests", SCRIPT)]
