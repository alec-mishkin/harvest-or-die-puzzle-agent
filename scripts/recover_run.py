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

    sim = make_sim(args.level)
    limit = sim.level.turn_limit
    has_predators = bool(sim.level.spawn_points)

    outcomes, turns, win_turns = Counter(), [], []
    episode_results = []

    for f in sorted(tdir.glob("ep*.jsonl")):
        lines = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        res = classify(lines, limit)
        outcomes[res] += 1
        episode_results.append(res)
        if res not in ("UNRESOLVED","EMPTY"):
            turns.append((len(lines)))
            if res = "WIN":
                win_turns.append(len(lines))
    completed = sum(v for k, v in outcomes.items() if k not in ("UNRESOLVED", "EMPTY"))

    if completed == 0:
        ap.error("no completed episodes found")

    record = {
        "run_id": args.run_id
        "timestamp": None,
        "git_sha": "reconstructed",
        "agent": "OpenAIAgent",
        "agent_config": {
            "model": args.model,
            "prompt_version": args.prompt_version
            "show_fatal": args.show_fatal,
            "show_futile": args.show_futile,
        }
        "level": args.level,
        "episodes": len(episode_results),
        "competed": completed,
        "seed_start": 0,
        "outcomes": dict(outcomes),
        "episode_results": episode_results,
        "win_rate": outcomes["WIN"] / completed,
        "mean_turns": sum(turns) / len(turns),
        "mean_win_turns": (sum(win_turns)/len(win_turns)) if win_turns else None,
        "input_tokes": None,
        "output_tokens": None,
        "transcripts": str(tdir.relative_to("REPO_ROOT")),
        "notes": (args.notes + " [RECONSTRUCTED from transcripts after an interrupted "
                  "run; rates are over `completed`, token counts unavailable]").strip(),
    }

    print(json.dumps(record, indent=2))
    print()
    print(f"completed={completed}  win_rate={record['win_rate']:.1%}  "
          f"mean_turns={record['mean_turns']:.1f}")
 
    if outcomes["UNRESOLVED"]:
        print(f"\n{outcomes['UNRESOLVED']} UNRESOLVED episode(s) excluded from rates.")
        if has_predators:
            print("  WARNING: this level has predators, so UNRESOLVED conflates CORNERED "
                  "with episodes cut off mid-flight. Treat the cornering rate as unknown.")
        else:
            print("  No predators on this level, so these are episodes cut off mid-flight.")
 
    if args.append:
        with RESULTS.open("a") as fh:
            fh.write(json.dumps(record) + "\n")
        print(f"\nappended to {RESULTS}")
    else:
        print("\n(not written -- pass --append to add it to runs.jsonl)")
 
 
if __name__ == "__main__":
    main()
