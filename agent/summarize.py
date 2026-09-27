import argparse, json
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--notes", action="store_true", help="show the notes field")
args = ap.parse_args()

rows = [json.loads(l) for l in Path("results/runs.jsonl").read_text().splitlines() if l.strip()]

hdr = f"{'run_id':22} {'agent':14} {'level':9} {'config':38} {'n':>5} {'win%':>6} {'death%':>7} {'cornered%':>7} {'turns':>6}"
if args.notes:
    hdr += "  notes"
print(hdr)
print("-" * len(hdr))
for r in rows:
    o,n = r["outcomes"], r["episodes"]
    cfg = ", ".join(f"{k}={v}" for k, v in r["agent_config"].items())
    line = (f"{r['run_id']:22} {r['agent']:14} {r['level']:9} {cfg:38} {n:5} "
          f"{r['win_rate']*100:5.1f}% {o.get('DEATH',0)/n*100:6.1f}% {o.get('CORNERED',0)/n*100:6.1f}% {r['mean_turns']:6.1f}")
    if args.notes:
        line += f"  {r.get('notes','')}"
    print(line)
