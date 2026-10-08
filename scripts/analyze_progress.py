import json, glob, sys
from collections import defaultdict
from game.levels import make_sim
from interface.adapter import Outcome, step
from statistics import mean

CODE = {"up": "U", "down": "D", "left": "L", "right": "R", None: None}
run_dir, level = sys.argv[1], sys.argv[2]
sim = make_sim(level)
by_outcome = defaultdict(list)

for f in sorted(glob.glob(f"{run_dir}/ep*.jsonl")):
    turns = [json.loads(l) for l in open(f)]
    state = sim.initial_state()
    hs, seeds, final = [], [], "TIMEOUT"

    for t in turns:
        h, _raw, _blobs = sim._heuristic_detail(state)
        hs.append(h)
        seeds.append(state.seed)
        outcome, state, _ = step(sim, state, CODE[t["harvest"]], CODE[t["move"]])
        if outcome is Outcome.ILLEGAL:
            print(f"REPLAY MISMATCH in {f}"); break
        if outcome in (Outcome.WIN, Outcome.DEATH):
            final = outcome.value.upper(); break
    if not hs:
        continue

    by_outcome[final].append({
        "regressions": sum(1 for a, b in zip(hs, hs[1:]) if b > a),
        "max_h": max(hs),
        "start_h": hs[0],
        "cleared_blobs": min(hs) <= 1,              # ever got all blobs cleared
        "seed_switches": sum(1 for a, b in zip(seeds, seeds[1:]) if a != b),
        "turns": len(hs),
    })

print(f"{'outcome':10} {'n':>4} {'regress':>8} {'max_h':>7} {'cleared':>8} {'switches':>9} {'turns':>6}")
for out, eps in sorted(by_outcome.items()):
    print(f"{out:10} {len(eps):4} "
        f"{mean(e['regressions'] for e in eps):8.2f} "
        f"{mean(e['max_h'] for e in eps):7.2f} "
        f"{mean(e['cleared_blobs'] for e in eps):8.0%} "
        f"{mean(e['seed_switches'] for e in eps):9.2f} "
        f"{mean(e['turns'] for e in eps):6.1f}")
