from verifierguard.cheaters.base import Attempt, Cheater, CheaterResult
from verifierguard.cheaters.do_nothing import DoNothing
from verifierguard.cheaters.hard_code import HardCode
from verifierguard.cheaters.tamper import Tamper
from verifierguard.cheaters.test_peek import TestPeek


def all_cheaters() -> list[Cheater]:
    return [DoNothing(), HardCode(), TestPeek(), Tamper()]


__all__ = [
    "Attempt",
    "Cheater",
    "CheaterResult",
    "DoNothing",
    "HardCode",
    "Tamper",
    "TestPeek",
    "all_cheaters",
]
