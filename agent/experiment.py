import json, subprocess, time
from collections import Counter
from pathlib import Path

RESULTS = Path("results/runs.jsonl")

def git_sha():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True)
        dirty = subprocess.run(["git", "status", "--porcelain"],
                               capture_output=True, text=True).stdout.strip()
        return out.stdout.strip() + ("-dirty" if dirty else "")
    except Exception:
        return "unknown"

def run_experiment(make_agent_fn, sim, level_name, episodes, seed_start=0, notes=""):
    outcomes, turns, win_turns = Counter(), [], []

    for i in range(episodes):
        agent = make_agent_fn(seed_start + i)
        result, history = play_episode(agent, sim, verbose=False)
        outcomes[result] += 1
        turns.append(len(history))
        if result == "WIN":
            win_turns.append(len(history))
    
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_sha": git_sha(),
        "agent": type(agent).__name__,
        "agent_config": getattr(agent, "config", lambda: {})(),
        "level": level_name,
        "episodes": episodes,
        "seed_start": seed_start,
        "outcomes": dict(outcomes),
        "win_rate": outcomes["WIN"] / episodes,
        "mean_turns": sum(turns) / len(turns),
        "mean_win_turns": sum(win_turns) / len(win_turns) if win_turns else None,
        "notes": notes,
    }

    RESULTS.parent.mkdir(exist_ok=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record

