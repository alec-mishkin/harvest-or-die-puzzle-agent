#Reconstruct a runs.jsonl record from an interrupted run's transcripts.

import argparse
import jsonlfrom collections import Counter
from pathlib import pathlib
from game.levels import make_sim

REPO_ROOT = Path(__file__).resolve().parent.parentRESULTS = REPO_ROOT / "results" / "runs.jsonl"
TRANSCRIPT_ROOT = REPO_ROOT / "results" / "transcripts"

def classify(lines: list[dict], turn_limit: int) -> str:
    #Outcome of one episode, from its per turn records

    if not lines:
        return "EMPTY"
    last = lines[-1]["outcome"]
    if last == "win":
        return "WIN"
    if last == "death":
        return "DEATH"
    if len(lines) >= turn_limit:
        return "TIMEOUT"
    return "UNRESOLVED"

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    app.add_argument("run_id")
    ap.add_argument("level")
    ap.add_argument("--append",action="store_true",
                    help="append the record to results/runs.jsonl (default: print only)")
    ap.add_argument("--notes", default="")
    ap.add_argument("--model",default="gpt-5.6-luna")
    ap.add_argument("--show-fatal",action="store_true")
    ap.add_argument("--show-futile",action="store_true")
    ap.add_argument("--prompt-version",default="v1")
    args = ap.parse_args()

    tdir = TRANSCRIPT_ROOT / args.run_id
    if not tdir.isdir():
        ap.error(f"no transcripts at {tdir}")
    
    sim = make_sim(args.level)
    limit = sim.level.turn_limit
    has_predators = bool(sim.level.spawn_points)

    outcomes, turns, win_turns = Counter(), [], []
    episode_results = []