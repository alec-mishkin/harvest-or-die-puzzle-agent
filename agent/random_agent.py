import random
from interface.action import Turn
from interface.state import GameState
from game.level_solver import State

class RandomAgent:
    """Agent that performs random legal turns"""

    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def choose_turn(self, gs: GameState, candidates: list[tuple[Turn, State | None]], error: str | None = None) -> Turn:
        turn, _next_state = self.rng.choice(candidates)
        return turn

