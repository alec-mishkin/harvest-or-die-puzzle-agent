import json
from pathlib import Path

rows = [json.loads(l) for l in Path("results/runs.jsonl").read_text().splitlines() if l.strip()]

hdr = f"{'run_id':22} {'agent':14} {'level':9} {'config':38} {'n':>5} {'win%':>6} {'death%':>7} {'cornered%':>7} {'turns':>6}"
print(hdr)
print("-" * len(hdr))
for r in rows:
    o = r["outcomes"]
    n = r["episodes"]
    cfg = ", ".join(f"{k}={v}" for k, v in r["agent_config"].items())
    print(f"{r['run_id']:22} {r['agent']:14} {r['level']:9} {cfg:38} {n:5} "
          f"{r['win_rate']*100:5.1f}% {o.get('DEATH',0)/n*100:6.1f}% {o.get('CORNERED',0)/n*100:6.1f}% {r['mean_turns']:6.1f}")
