import json, glob, sys
from collections import defaultdict
from game.levels import make_sim
from interface.adapter import Outcome, is_futile_harvest, step
from statistics import mean
import re


CODE = {"up": "U", "down": "D", "left": "L", "right": "R", None: None}
run_dir, level = sys.argv[1], sys.argv[2]
sim = make_sim(level)
by_outcome = defaultdict(list)

SEED_RE  = re.compile(r"Held seed: (\w+)")
TALLY_RE = re.compile(r"Currently: (.+)")


for f in sorted(glob.glob(f"{run_dir}/ep*.jsonl")):
    turns = [json.loads(l) for l in open(f)]
    state = sim.initial_state()
    hs, seeds, final, futile = [], [], "TIMEOUT", 0

    for t in turns:
        seed  = SEED_RE.search(t["prompt"]).group(1) 
        tally = TALLY_RE.search(t["prompt"]).group(1)
        shown_seed = SEED_RE.search(t["prompt"]).group(1).upper()
        true_seed  = state.seed.name
        if shown_seed != true_seed:
            print(f"SEED MISMATCH {f} turn {t['turn']}: shown={shown_seed} true={true_seed}")
        h, _raw, _blobs = sim._heuristic_detail(state)
        hs.append(h)
        seeds.append(state.seed)
        if is_futile_harvest(sim, state, CODE[t["harvest"]]):
            futile += 1   
        outcome, state, _ = step(sim, state, CODE[t["harvest"]], CODE[t["move"]])
        if outcome is Outcome.ILLEGAL:
            print(f"REPLAY MISMATCH in {f}"); break
        if outcome in (Outcome.WIN, Outcome.DEATH):
            final = outcome.value.upper(); break
    if not hs:
        continue
    first_clear = next((i for i, h in enumerate(hs) if h <= 1), None)
    by_outcome[final].append({
        "name": f.split("/")[-1].replace(".jsonl", ""),
        "regressions": sum(1 for a, b in zip(hs, hs[1:]) if b > a),
        "max_h": max(hs),
        "start_h": hs[0],
        "cleared_blobs": min(hs) <= 1,              # ever got all blobs cleared
        "seed_switches": sum(1 for a, b in zip(seeds, seeds[1:]) if a != b),
        "turns": len(hs),
        "first_clear": first_clear,
        "moves_left": (sim.level.turn_limit - first_clear) if first_clear is not None else None,
        "harvest_at_clear": turns[first_clear]["harvest"] if first_clear is not None else None,
        "move_at_clear": turns[first_clear]["move"] if first_clear is not None else None,
        "futile": futile,
        "any_futile": futile > 0,
    })

print(f"{'outcome':10} {'n':>4} {'regress':>8} {'max_h':>7} {'cleared':>8} {'switches':>9} {'turns':>6}")
for out, eps in sorted(by_outcome.items()):
    cl = [e for e in eps if e["first_clear"] is not None]
    clear_at = f"{mean(e['first_clear'] for e in cl):7.1f}" if cl else f"{'-':>7}"
    moves_left = f"{mean(e['moves_left'] for e in cl):10.1f}" if cl else f"{'-':>10}"
    print(f"{out:10} {len(eps):4} "
        f"{mean(e['regressions'] for e in eps):8.2f} "
        f"{mean(e['max_h'] for e in eps):7.2f} "
        f"{mean(e['cleared_blobs'] for e in eps):8.0%} "
        f"{mean(e['seed_switches'] for e in eps):9.2f} "
        f"{mean(e['turns'] for e in eps):6.1f}"
        f"{mean(e['futile'] for e in eps):7.2f} "
        f"{mean(e['any_futile'] for e in eps):8.0%} "
        f"{clear_at} {moves_left}")

near = [e for e in by_outcome.get("TIMEOUT", []) if e["first_clear"] is not None]
print(f"\n--- TIMEOUT episodes that reached h<=1  (n={len(near)}) ---")
for e in sorted(near, key=lambda e: e["moves_left"], reverse=True):
    print(f"{e['name']:8} cleared at turn {e['first_clear']:2}  "
    f"{e['moves_left']:2} move(s) left  "
    f"harvest={str(e['harvest_at_clear']):5} move={e['move_at_clear']}")




