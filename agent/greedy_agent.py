import random

class GreedyAgent:
    """One-step lookahead on the solver's admissible distance-to-goal bound.
    Skips fatal moves, then minimizes (h, blobs)."""

    def __init__(self, sim, seed=None, key="h_first"):
        self.sim = sim
        self.rng = random.Random(seed)
        self.key = key

    def _score(self, h, blobs):
        return (h, blobs) if self.key == "h_first" else (blobs, h)
    
    def config(self):
        return {"key": self.key}

    def choose_turn(self, gs, candidates, error=None):
        survivable = [(t, s) for t, s in candidates if s is not None]
        if not survivable:
             return self.rng.choice([t for t, _ in candidates]) #death is inevitable

        scored = []
        for turn, next_state in survivable:
            h, _raw, blobs = self.sim._heuristic_detail(next_state)
            scored.append((self._score(h, blobs), turn))

        best = min(s for s, _ in scored)
        return self.rng.choice([t for s, t in scored if s == best])

