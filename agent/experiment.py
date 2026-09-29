import json, subprocess, time
import argparse, json
import uuid
from agent.play import play_episode
from agent.greedy_agent import GreedyAgent
from agent.random_agent import RandomAgent
from agent.openai_agent import OpenAIAgent
from game.levels import make_sim


from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS = REPO_ROOT / "results" / "runs.jsonl"
TRANSCRIPT_ROOT = REPO_ROOT / "results" / "transcripts"


def git_sha():
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        raw = subprocess.run(["git", "status", "--porcelain"],
                             capture_output=True, text=True).stdout
        changes = [l for l in raw.splitlines() if not l[3:].startswith("results/")]
        return sha + ("-dirty" if changes else "")

    except Exception:
        return "unknown"

def run_experiment(make_agent_fn, sim, level_name, episodes, seed_start=0, notes="",transcripts=False, workers=1):
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
    tdir = TRANSCRIPT_ROOT / run_id 
    if transcripts:
        tdir.mkdir(parents=True, exist_ok=True)

    outcomes, turns, win_turns, episode_results = Counter(), [], [], []
    in_tok = out_tok = 0
    def run_one(i): 
        agent = make_agent_fn(seed_start + i)
        f = (tdir / f"ep{i:03d}.jsonl").open("w") if transcripts else None

        def on_turn(rec, _f=f):
            if _f:
                _f.write(json.dumps(rec) + "\n")
                _f.flush()
        try:
            result, history = play_episode(agent, sim, verbose=False, on_turn=on_turn)
        finally:
            if f:
                f.close()
        print(f"  ep{i:03d}: {result}", flush=True)
        return i, result, len(history), agent.input_tokens, agent.output_tokens
    meta_agent = make_agent_fn(seed_start)     # for config/type only; makes no API call
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(run_one, range(episodes)))

    results.sort()          # ex.map preserves order, but be explicit
    outcomes, turns, win_turns, episode_results = Counter(), [], [], []
    in_tok = out_tok = 0
    for _i, result, n_turns, i_tok, o_tok in results:
        outcomes[result] += 1
        episode_results.append(result)
        turns.append(n_turns)
        if result == "WIN":
            win_turns.append(n_turns)
        in_tok += i_tok
        out_tok += o_tok

    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "git_sha": git_sha(),
        "agent": type(meta_agent).__name__,
        "agent_config": meta_agent.config() if hasattr(meta_agent, "config") else {},
        "level": level_name,
        "episodes": episodes,
        "seed_start": seed_start,
        "outcomes": dict(outcomes),
        "win_rate": outcomes["WIN"] / episodes,
        "mean_turns": sum(turns) / len(turns),
        "mean_win_turns": sum(win_turns) / len(win_turns) if win_turns else None,
        "notes": notes,
        "run_id": run_id,
        "episode_results": episode_results,
        "input_tokens":i_tok,
        "output_tokens":o_tok,
        "transcripts": str(tdir) if transcripts else None,
    }

    RESULTS.parent.mkdir(exist_ok=True)
    with RESULTS.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return record

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=["random", "greedy", "openai"], default="greedy")
    ap.add_argument("--key", choices=["h_first", "blobs_first"], default="h_first")
    ap.add_argument("--level", default="level_3")
    ap.add_argument("--episodes", type=int, default=1000)
    ap.add_argument("--seed-start", type=int, default=0)
    ap.add_argument("--notes", default="")
    ap.add_argument("--transcripts", action="store_true")
    ap.add_argument("--show-fatal", action="store_true")
    ap.add_argument("--workers", type=int, default=1)
    args = ap.parse_args()

    sim = make_sim(args.level)

    def factory(seed):
        if args.agent == "random":
            return RandomAgent(seed=seed)
        if args.agent == "greedy":
            return GreedyAgent(sim, seed=seed, key=args.key)
        if args.agent == "openai":
             return OpenAIAgent(model="gpt-5.6-luna", show_fatal=args.show_fatal)
    
    record = run_experiment(factory, sim, args.level, args.episodes,
                            args.seed_start, args.notes, args.transcripts)

    print(json.dumps(record, indent=2))

