"""ERL->IRL ablation — validity diagnostics behind the frozen rungs.

Run AFTER the frozen ladder (erlirl_ablation.py); this script exists to
characterize WHY the frozen result looks the way it does, so the record
discloses measure-validity limits instead of silently reporting them.
Zero spend, zero outcomes redefinition — INPUT-side geometry only.

1. Rung-2 saturation: distribution of contrast_R on rung 2 (share at
   the +2.5/-2.5 winsorized bounds) and WHY the frame is selection-
   bound (displacement = the reversal is required BEFORE the entry
   stamp; contrast arm asymmetry T=+2 vs S=-0.5 makes the conditioning
   event mechanically fire the continuation arm's stop).
2. Rung-3 emptiness: the frozen definition (d.low > touch.high — a
   whole-bar jump clearing the touch bar) yields n=0. Count how close
   it comes: fraction of rung-2 events with gap excess > k xATR for
   k in {0, 0.25, 0.5, 1.0} — and the STANDARD three-bar FVG form
   (C1 scifvg_main.py:413-421 convention: c0.low > c2.high over three
   bars), evaluated forward from the touch bar within 6 bars.
3. ATR floor sanity: median touch-bar range vs the jump requirement.

Bars are cached once to data/databento/erlirl_bars_{mkt}.pkl (git-
ignored dir) because decoding the full series costs ~8 min per market.

  python erlirl_diagnostics.py
"""
import json
import os
import pickle
from datetime import date, timedelta

import numpy as np

import databento_local_data as dld
import erlirl_ablation as ea
from c2_local_study import DEV_START

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "data", "databento")


def cached_bars_events(market, imap):
    pkl = os.path.join(CACHE, f"erlirl_bars_{market}.pkl")
    if os.path.exists(pkl):
        with open(pkl, "rb") as fh:
            return pickle.load(fh)
    bars, events = ea.load_bars_and_events(market, imap)
    # strip tzinfo-free datetimes are picklable; keep (et naive) as-is
    os.makedirs(CACHE, exist_ok=True)
    with open(pkl, "wb") as fh:
        pickle.dump((bars, events), fh)
    return bars, events


def main():
    imap = dld.load_instrument_map()
    out = {}
    for market in ("NQ", "GC"):
        bars, events = cached_bars_events(market, imap)
        bar_at = {b["et"]: i for i, b in enumerate(bars)}
        stats = {"events": len(events)}
        sat = {}
        jump_excess = []
        std3 = {"fwd": 0, "any": 0}
        touch_ranges = []
        for (et, side, level, atr, ctx) in events:
            i0 = bar_at[et]
            touch = bars[i0]
            touch_ranges.append(touch["high"] - touch["low"])
            d = ea.displacement_idx(bars, i0, side, level)
            if d is None:
                continue
            dd = bars[d]
            # frozen rung-3 jump condition, measured as excess in ATRs
            excess = ((dd["low"] - touch["high"]) if side > 0
                      else (touch["low"] - dd["high"])) / atr
            jump_excess.append(excess)
            # standard three-bar FVG (C1 form) forward from touch bar:
            # long reversal (low touch) wants a DOWN gap? C1 for side>0
            # wants c0.low > c2.high (downward void left by an UP move?
            # no — C1 side>0 = long reversal after sweep of a LOW; the
            # displacement is UP; the void for a retrace-down is
            # c0.low > c2.high where c0 is earlier). Mirror C1 exactly.
            hit = False
            for j in range(i0, min(i0 + 7, len(bars) - 2)):
                c0, c2 = bars[j], bars[j + 2]
                if side > 0 and c0["low"] > c2["high"]:
                    hit = True
                    break
                if side < 0 and c0["high"] < c2["low"]:
                    hit = True
                    break
            std3["any"] += 1
            if hit:
                std3["fwd"] += 1
        jump_excess = np.array(jump_excess)
        stats["rung2_candidates"] = int(len(jump_excess))
        for k in (0.0, 0.25, 0.5, 1.0):
            stats[f"jump_excess_gt_{k}atr"] = int((jump_excess > k).sum())
        stats["standard_3bar_fvg_within6"] = std3
        stats["median_touch_range_points"] = float(np.median(touch_ranges))
        stats["median_atr_points"] = float(np.median(
            [a for (*_, a, _c) in events])) if events else None
        out[market] = stats
    # rung2 saturation straight from the frozen artifact (no bars needed)
    led = json.load(open(os.path.join(HERE, "erlirl_ablation.json"),
                         encoding="utf-8"))
    for market in ("NQ", "GC"):
        c = np.array([x["contrast_R"] for x in led[market]["rungs"]["2"]])
        out[market]["rung2_saturation"] = {
            "n": int(c.size),
            "share_plus_bound": float(np.mean(c >= 2.5 - 1e-12)),
            "share_minus_bound": float(np.mean(c <= -2.5 + 1e-12)),
            "share_zero": float(np.mean(c == 0.0))}
    json.dump(out, open(os.path.join(HERE, "erlirl_diagnostics.json"), "w"),
              indent=1)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
