import random
from interface.action import Turn
from interface.state import GameState

class RandomAgent:
    """Agent that performs random legal turns"""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def choose_turn(self, gs: GameState, legal: list[Turn], error: str | None = None) -> Turn:
        return self.rng.choice(legal)

