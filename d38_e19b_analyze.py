"""E19B bootstrap: pre-registered analysis on the exported event ledgers.

Population: bias_aligned==True rows pooled ACROSS MARKETS (never across
arms). Delta = mean side-aligned forward R at each horizon. Session-block
(day-level) bootstrap, percentile 95% CI. Three-outcome rule anchored on
theta=0.2R per PREREGISTRATION_E19B.md section 4 (amended).

Run:  python d38_e19b_analyze.py
Reads: e19b_ledgers/{NQ,ES,YM,RTY}_events.jsonl
Writes: E19B_ANALYSIS.md + prints the table.
"""
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
THETA = 0.2
HORIZONS = (30, 60, 120, 240)
MARKETS = ("NQ", "ES", "YM", "RTY")


def load():
    rows = []
    for inst in MARKETS:
        p = os.path.join(ROOT, "e19b_ledgers", f"{inst}_events.jsonl")
        for line in open(p, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                if r.get("bias_aligned"):
                    rows.append(r)
    return rows


def boot_ci(by_day, B, alpha, rng):
    day_lists = list(by_day.values())
    means = []
    for _ in range(B):
        tot = cnt = 0.0
        for _d in range(len(day_lists)):
            j = rng.randrange(len(day_lists))
            pick = day_lists[j]
            tot += sum(pick)
            cnt += len(pick)
        if cnt:
            means.append(tot / cnt)
    means.sort()
    allv = [v for dl in day_lists for v in dl]
    obs = sum(allv) / len(allv) if allv else float("nan")
    lo = means[int((alpha / 2) * len(means))]
    hi = means[min(len(means) - 1, int((1 - alpha / 2) * len(means)))]
    return obs, lo, hi


def main():
    rows = load()
    print(f"loaded {len(rows)} aligned rows")
    out = ["# E19B ANALYSIS — pre-registered rule applied offline",
           "",
           "Population: bias_aligned == True, pooled across markets.",
           "Rule: POSITIVE if CI_lo > 0.2R; NULL if CI_hi < 0.2R; else "
           "INCONCLUSIVE.", "",
           "| horizon | n | mean R | CI lo | CI hi | verdict |",
           "|---|---|---|---|---|---|"]
    rng = random.Random(20260825)
    verdicts = {}
    for h in HORIZONS:
        sel = [r for r in rows if r["h_min"] == h]
        by_day = {}
        per_mkt = {}
        for r in sel:
            y = r["raw"]["y"]
            key = f"{r['inst']}:{r['raw']['x'] // 86400}"
            by_day.setdefault(key, []).append(y)
            per_mkt.setdefault(r["inst"], []).append(y)
        obs, lo, hi = boot_ci(by_day, 3000, 0.05, rng)
        v = ("POSITIVE" if lo > THETA
             else "NULL" if hi < THETA else "INCONCLUSIVE")
        verdicts[h] = v
        out.append(f"| {h}m | {len(sel)} | {obs:.4f} | {lo:.4f} | "
                   f"{hi:.4f} | **{v}** |")
        detail = ", ".join(f"{m} {sum(v)/len(v):+.3f}"
                           for m, v in sorted(per_mkt.items()))
        out.append(f"    - per-market means: {detail}")
    primary = verdicts[120]
    out.append("")
    out.append(f"PRIMARY (H*=120m): **{primary}**")
    out.append("")
    out.append(f"All horizons: " + ", ".join(f"{h}m={verdicts[h]}"
                                             for h in HORIZONS))
    out.append("")
    out.append("## Pre-run power diagnostic (MDE)")
    out.append("Day-level SD of aligned forward R across ~3.7k market-days; "
               "with n=1381 events / ~3.5y and day-clustered resampling, "
               "design MDE at 80% power / alpha=0.05 is ~0.20-0.25R - the "
               "study resolves barely to the friction bar itself.")
    report = "\n".join(out)
    print(report)
    with open(os.path.join(ROOT, "E19B_ANALYSIS.md"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(report + "\n")


if __name__ == "__main__":
    main()
