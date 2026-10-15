import argparse, json
from pathlib import Path
def win_ci(wins: int, n: int) -> tuple[float, float]:
    """95% Wilson score interval on the win rate."""
    from statsmodels.stats.proportion import proportion_confint
    return proportion_confint(count=wins, nobs=n, alpha=0.05, method="wilson")

ap = argparse.ArgumentParser()
ap.add_argument("--notes", action="store_true", help="show the notes field")
ap.add_argument("--clean", action="store_true",help="only show runs from a clean commit")
ap.add_argument("--ci", action="store_true",help="add a 95%% Wilson CI (needs 'analysis')")
ap.add_argument("--level", help="filter to one level, e.g. level_6")
ap.add_argument("--agent", help="filter to one agent class, e.g. greedy")


args = ap.parse_args()
if args.ci:
    try:
        from statsmodels.stats.proportion import proportion_confint  # noqa: F401
    except ImportError:
        ap.error('--ci needs statsmodels: pip install -e ".[analysis]"')


rows = [json.loads(l) for l in Path("results/runs.jsonl").read_text().splitlines() if l.strip()]
if args.clean:
    rows = [r for r in rows if "-dirty" not in r.get("git_sha", "")]
if args.level:
    rows = [r for r in rows if r["level"] == args.level]
if args.agent:
    rows = [r for r in rows if r["agent"].lower().startswith(args.agent.lower())]

hdr = f"{'run_id':22} {'agent':14} {'level':9} {'config':38} {'n':>5} {'win%':>6} {'death%':>7} {'cornered%':>7} {'turns':>6}"
if args.ci:
    hdr += f" {'win 95% CI':>15}"
if args.notes:
    hdr += "  notes"
print(hdr)
print("-" * len(hdr))
for r in rows:
    o,n = r["outcomes"], r["episodes"]
    cfg = ", ".join(f"{k}={v}" for k, v in r["agent_config"].items())
    line = (f"{r['run_id']:22} {r['agent']:14} {r['level']:9} {cfg:38} {n:5} "
          f"{r['win_rate']*100:5.1f}% {o.get('DEATH',0)/n*100:6.1f}% {o.get('CORNERED',0)/n*100:6.1f}% {r['mean_turns']:6.1f}")
    if args.ci:
        lo, hi = win_ci(o.get("WIN", 0), n)
        line += f"   [{lo*100:4.1f}-{hi*100:5.1f}]"
    if args.notes:
        line += f"  {r.get('notes','')}"
    print(line)

