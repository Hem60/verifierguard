from verifierguard.cheaters.base import Attempt, Cheater
from verifierguard.models import Task


class DoNothing(Cheater):
    name = "do_nothing"
    meaning = "Verifier is broken or checks too little: it passes an untouched environment."

    def attempts(self, task: Task) -> list[Attempt]:
        return [Attempt("empty", "#!/bin/bash\ntrue\n")]
