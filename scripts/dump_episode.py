import json, sys
from game.levels import make_sim
from game.level_solver import CT
from interface.adapter import Outcome, step

CODE = {"up": "U", "down": "D", "left": "L", "right": "R", None: None}

path, level = sys.argv[1], sys.argv[2]
sim = make_sim(level)
s = sim.initial_state()
turns = [json.loads(l) for l in open(path)]
print(f"turn_limit={sim.level.turn_limit}  recorded_turns={len(turns)}")

for t in turns:
    tally = {}
    for pos in sim.scored_cells:
        if pos in sim.plant_index:
            key = (sim.cell_color(s, pos).name,
                "hole" if sim.cell_type(s, pos) == CT.HOLE else "plant")
            tally[key] = tally.get(key, 0) + 1
    h, _, _ = sim._heuristic_detail(s)
    nw = len({sim.cell_color(s, p) for p in sim.scored_cells if p in sim.plant_index}) <= 1
    print(f"T{s.turn:2} h={h} near_win={nw} seed={s.seed.name:6} {tally}")
    out, s, msg = step(sim, s, CODE[t["harvest"]], CODE[t["move"]])
    print(f"     harvest={t['harvest']} move={t['move']} -> {out.value} {msg}")
    if out in (Outcome.WIN, Outcome.DEATH):
        break
print(f"ended at turn={s.turn}")

