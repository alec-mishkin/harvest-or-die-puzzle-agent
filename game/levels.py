from pathlib import Path

from game.level_solver import build_level, Sim

LEVELS_DIR = Path(__file__).resolve().parent / "levels"

LEVELS = {
            "level_14" : ("level_14.csv", "level_14_stats.asset"),
            "level_3" : ("level_3.csv", "level_3_stats.asset"),
            }

def make_sim(name: str) -> Sim:
    csv_name, stats_name = LEVELS[name]
    level = build_level(LEVELS_DIR / csv_name, LEVELS_DIR / stats_name)
    return Sim(level, max_turn=level.turn_limit)

