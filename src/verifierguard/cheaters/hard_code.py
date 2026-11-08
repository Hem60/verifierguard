from verifierguard.cheaters.base import Attempt, Cheater
from verifierguard.loader import candidate_output_paths
from verifierguard.models import Task

PLACEHOLDERS = ("0", "1", "42", "placeholder")


class HardCode(Cheater):
    name = "hard_code"
    meaning = "Verifier accepts a made up answer: it checks presence or a guessable value only."

    def attempts(self, task: Task) -> list[Attempt]:
        paths = candidate_output_paths(task) or [f"{task.workdir.rstrip('/')}/answer.txt"]
        attempts = []
        for value in PLACEHOLDERS:
            lines = ["#!/bin/bash"]
            for path in paths:
                lines.append(f"mkdir -p \"$(dirname '{path}')\"")
                lines.append(f"printf '%s\\n' '{value}' > '{path}'")
            attempts.append(Attempt(f"write {value!r}", "\n".join(lines) + "\n"))
        return attempts
