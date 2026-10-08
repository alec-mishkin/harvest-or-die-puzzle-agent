import json, glob, sys
from game.levels import make_sim
from interface.adapter import Outcome, step

CODE = {"up": "U", "down": "D", "left": "L", "right": "R", None: None}

run_dir, level = sys.argv[1], sys.argv[2]
sim = make_sim(level)

for f in sorted(glob.glob(f"{run_dir}/ep*.jsonl")):
    turns = [json.loads(l) for l in open(f)]
    state = sim.initial_state()
    hs, final = [], "TIMEOUT"

    for t in turns:
        h, _raw, _blobs = sim._heuristic_detail(state)
        hs.append(h)
        outcome, state, _ = step(sim, state, CODE[t["harvest"]], CODE[t["move"]])

        if outcome in (Outcome.WIN, Outcome.DEATH):
            final = outcome.value.upper()
            break

    # did h ever go UP? (thrashing) and how far did it get?
    regressions = sum(1 for a, b in zip(hs, hs[1:]) if b > a)
    print(f"{f.split('/')[-1]:12} {final:8} h: {hs}  regressions={regressions}  net={hs[0]-hs[-1]}")
