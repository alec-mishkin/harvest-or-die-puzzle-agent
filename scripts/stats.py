import argparse
import json
import math
import warnings
from pathlib import Path

import scipy.optimize as opt 
from scipy.stats import fisher_exact
from statsmodels.stats.power import zt_ind_solve_power
from statsmodels.stats.proportion import (
    proportion_confint,
    proportion_effectsize,
    proportions_ztest,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS = REPO_ROOT / "results" / "runs.jsonl"

def load_runs() -> dict[str, dict]:
    rows = [json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()]
    return {r["run_id"]: r for r in rows}

def group_counts(runs: dict, ids: list[str], outcome: str) -> tuple[int, int, list[str]]:
    """Pooled (successes, trials)) for onegroup"""

    k = n = 0
    labels = []
    for rid in ids:
        if rid not in runs:
            raise SystemExit(f"run_id not found in runs.jsonl : {rid}")
        r = runs[rid]
        ki = r["outcomes"].get(outcome, 0)
        ni = r.get("completed") or r["episodes"]
        k += ki
        n += ni
        cfg = ", ".join(f"{a}={b}" for a, b in r["agent_config"].items())
        labels.append(f"    {rid}  {r['agent']:12} {r['level']:9} "
                      f"{ki:4}/{ni:<5} {ki/ni:6.1%}   {cfg}")
    return k, n, labels

def compare(args):
    runs = load_runs()
    outcome = args.outcome.upper()
    
    if "vs" not in args.ids:
         raise SystemExit("separate the two groups with the literal word 'vs'")
    split = args.ids.index("vs")
    a_ids, b_ids = args.ids[:split], args.ids[split + 1:]
    if not a_ids or not b_ids:
        raise SystemExit("need at least one run_id on each side of 'vs'")

    ka, na, la = group_counts(runs, a_ids, outcome)
    kb, nb, lb = group_counts(runs, b_ids, outcome)

    print(f"outcome: {outcome}\n")
    print("group A:")
    print("\n".join(la))
    print("group B:")
    print("\n".join(lb))
    print()

    for lbl, k, n in (("A", ka, na)), ("B", kb, nb):
        lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
        print(f"  pooled {lbl}: {k}/{n} = {k/n:.1%}   95% Wilson [{lo:.1%}-{hi:.1%}]")

    diff = kb / nb - ka / na
    print(f"\n  difference (B - A): {diff*100:+.1f} points")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        _, p_z = proportions_ztest([ka, kb], [na, nb])
    if math.isnan(p_z):
        p_z = 1.0
    _, p_f = fisher_exact([[ka, na-ka], [kb, nb-kb]])
    small = min(ka, na-ka, kb, nb - kb) < 5
    chosen, p = ("Fisher exact", p_f) if small else ("two-proportion z", p_z)
    
    print(f"\n  test: {chosen}" + ("  (a cell is < 5)" if small else ""))
    print(f"  p = {p:.3g}")
    if p_z > 0 and p_f > 0 and abs(math.log10(p_z) - math.log10(p_f)) > 1:
        print(f"  NOTE: the two tests disagree by >1 order of magnitude "
            f"(z={p_z:.2g}, fisher={p_f:.2g}); trust the exact test.")
    
    base = ka / na
    if 0 < base < 1:
        try: 
            det = opt.brentq(
                lambda t: zt_ind_solve_power(
                    effect_size=proportion_effectsize(t, base), alpha=0.05,
                    power=0.80, ratio=nb / na, alternative="two-sided") - na,
                    min(base + 1e-4, 0.999), 0.999)
            print(f"\n  at 80% power this design detects {base:.1%} -> {det:.1%} "
            f"({(det-base)*100:+.1f} points)")


        except ValueError:
            pass

def power(args):
    det = opt.brentq(
        lambda t: zt_ind_solve_power(
            effect_size=proportion_effectsize(t, args.baseline), alpha=0.05,
            power=0.80, ratio=args.n_b / args.n_a, alternative="two-sided") - args.n_a,
        args.baseline + 1e-4, 0.999)
    print(f"baseline {args.baseline:.1%}, n_a={args.n_a}, n_b={args.n_b}")
    print(f"  detects a shift to {det:.1%} ({(det-args.baseline)*100:+.1f} points) "
          f"at 80% power")
 
 
def size(args):
    es = proportion_effectsize(args.target, args.baseline)
    for pw in (0.80, 0.90):
        n = zt_ind_solve_power(effect_size=es, alpha=0.05, power=pw,
                               alternative="two-sided")
        print(f"  {args.baseline:.1%} -> {args.target:.1%} at {pw:.0%} power: "
              f"n = {math.ceil(n)} per arm")
 
 
def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
 
    c = sub.add_parser("compare", help="compare an outcome between two groups of runs")
    c.add_argument("outcome", help="WIN, DEATH, CORNERED, TIMEOUT")
    c.add_argument("ids", nargs="+", help="<run_ids...> vs <run_ids...>")
    c.set_defaults(fn=compare)
 
    p = sub.add_parser("power", help="what a planned design can detect")
    p.add_argument("--baseline", type=float, required=True)
    p.add_argument("--n-a", type=int, required=True)
    p.add_argument("--n-b", type=int)
    p.set_defaults(fn=power)
 
    s = sub.add_parser("size", help="episodes per arm for a given shift")
    s.add_argument("--baseline", type=float, required=True)
    s.add_argument("--target", type=float, required=True)
    s.set_defaults(fn=size)
 
    args = ap.parse_args()
    if getattr(args, "n_b", None) is None and args.cmd == "power":
        args.n_b = args.n_a
    args.fn(args)
 
 
if __name__ == "__main__":
    main()
