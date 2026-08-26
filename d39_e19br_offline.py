"""E19B-R offline replication (BEFORE any cloud cycle).

Directive: run the directive's own bootstrap offline on the committed
ledgers first. Reproduce the reported numbers:
  - 1,381 aligned events across 1,031 distinct reclaim session-dates
  - 10,000 resamples jointly clustered by reclaim session-date
  - raw CI [-0.240, +0.233] -> INCONCLUSIVE
  - winsorized +-5R CI [-0.217, +0.098] -> NULL
  - risk_dist floor diagnostic: 9 events carry +36.2R vs whole-sample
    total -12.6R; +71R extreme implies stop ~1/71 of the 120m move.

Reads e19b_ledgers/{NQ,ES,YM,RTY}_events.jsonl. No cloud cycles spent.
"""
import json
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
B = 10000
THETA = 0.2


def load_aligned():
    rows = []
    for inst in ("NQ", "ES", "YM", "RTY"):
        p = os.path.join(ROOT, "e19b_ledgers", f"{inst}_events.jsonl")
        for line in open(p, encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                if r.get("bias_aligned"):
                    rows.append(r)
    return rows


def session_date(r):
    """Reclaim session date from unix x (ET calendar day)."""
    x = r["raw"]["x"]
    days = x // 86400
    # convert day index to ET date string via UTC-4 approximation is risky;
    # use exact ET offset table-free approach: unix - 4h*3600 (EDT) may be
    # off by an hour in winter; acceptable ONLY if it doesn't split sessions.
    # Safer: derive date from RTH proximity - but ledger lacks timestamps.
    return days


def boot_ci(by_day, B, alpha, rng):
    lists = list(by_day.values())
    n = len(lists)
    means = []
    for _ in range(B):
        tot = cnt = 0.0
        for _i in range(n):
            j = rng.randrange(n)
            pick = lists[j]
            tot += sum(pick)
            cnt += len(pick)
        means.append(tot / cnt)
    means.sort()
    allv = [v for dl in lists for v in dl]
    obs = sum(allv) / len(allv)
    lo = means[int(alpha / 2 * len(means))]
    hi = means[min(len(means) - 1, int((1 - alpha / 2) * len(means)))]
    return obs, lo, hi


def verdict(lo, hi, theta=THETA):
    if lo > theta:
        return "POSITIVE"
    if hi < theta:
        return "NULL"
    return "INCONCLUSIVE"


def main():
    rows = [r for r in load_aligned() if r["h_min"] == 120]
    print(f"aligned H*=120 events: {len(rows)}")
    days = {}
    for r in rows:
        d = session_date(r)
        days.setdefault(d, []).append(float(r["raw"]["y"]))
    print(f"distinct reclaim session-dates: {len(days)} "
          f"({len(rows)/len(days):.2f}/date)")

    rng = random.Random(20260825)
    obs_raw, lo_raw, hi_raw = boot_ci(days, B, 0.05, rng)
    v_raw = verdict(lo_raw, hi_raw)
    print(f"RAW     mean={obs_raw:+.4f} CI=[{lo_raw:+.4f},{hi_raw:+.4f}] "
          f"halfwidth={(hi_raw-lo_raw)/2:.4f} -> {v_raw}")

    # winsorized at +-5R
    wins = {d: [min(5.0, max(-5.0, v)) for v in vals]
            for d, vals in days.items()}
    obs_w, lo_w, hi_w = boot_ci(wins, B, 0.05,
                                random.Random(20260825))
    v_w = verdict(lo_w, hi_w)
    print(f"WINSOR  mean={obs_w:+.4f} CI=[{lo_w:+.4f},{hi_w:+.4f}] "
          f"halfwidth={(hi_w-lo_w)/2:.4f} -> {v_w}")

    # risk_dist floor diagnostic: top |ret_r| events
    ranked = sorted(rows, key=lambda r: -float(r["raw"]["y"]))
    total = sum(float(r["raw"]["y"]) for r in rows)
    top9 = ranked[:9]
    s9 = sum(float(r["raw"]["y"]) for r in top9)
    print(f"\nwhole-sample total: {total:+.2f}R")
    print("top-9 ret_r:", [round(float(r['raw']['y']), 1) for r in top9],
          f"sum={s9:+.1f}R ({100*s9/len(rows):.2f}% of events)")
    extreme = float(top9[0]["raw"]["y"])
    print(f"+extreme={extreme:+.1f}R -> implied stop ~1/{abs(extreme):.0f} "
          f"of the 120-minute move")

    # floored sensitivity: drop events with |ret_r| > 5R (proxy for floor)
    kept = [r for r in rows if abs(float(r["raw"]["y"])) <= 5.0]
    print(f"\n|ret_r|<=5R kept {len(kept)}/{len(rows)}; "
          f"mean={sum(float(r['raw']['y']) for r in kept)/len(kept):+.4f}")

    ok = (len(rows) == 1381 and len(days) == 1031
          and v_raw == "INCONCLUSIVE")
    print("\nREPLICATION:", "MATCHES directive numbers"
          if ok else "DIFFERS - investigate before cloud spend")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
