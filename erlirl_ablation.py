"""ERL->IRL gate-ablation event study — ERLIRL_ABLATION_PROTOCOL.md.

Zero spend: replays the committed C2 event population against the same
guard-verified local Databento 30-minute bars c2_local_study.py used.
Exploratory; no promotion power; kill rule frozen at protocol S6.

  python erlirl_ablation.py

Pure gates (displacement_idx / void_edge / retrace_fill_idx /
opposing_liquidity / variable_target) are functions of bar PREFIXES
only and are pinned by test_erlirl_ablation_lookahead.py — the
Campaign 1 look-ahead defect class, guarded structurally.
"""
import hashlib
import json
import os
from datetime import date, timedelta

import numpy as np

import databento_local_data as dld
from c2_local_study import (DEV_START, HORIZONS, TICK, clustered_ci,
                            resolve_arm)

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "c2_local_study.json")
OUT = os.path.join(HERE, "erlirl_ablation.json")
REPORT = os.path.join(HERE, "erlirl_ablation_report.txt")
SEED_PREFIX = "ERLIRL-ABLATION-2026-09-05"
DEADLINE = 6          # protocol S3: fixed, all gates
WINDOW_BARS = 4       # 120 min of completed bars after the stamp
LIQ_LOOKBACK = 20     # protocol S4
STRUCT_BUFFER = 0.5   # xATR stop buffer beyond the sweep extreme
RISK_FLOOR = 0.25     # xATR floor on structural risk (S4)


def _rng(label):
    return np.random.default_rng(
        int(hashlib.sha256((SEED_PREFIX + label).encode()).hexdigest()[:16],
            16))


# ---------------------------------------------------------------- gates
def displacement_idx(bars, touch_i, side, level, deadline=DEADLINE):
    """Index of the first bar after touch_i (within deadline) whose
    CLOSE is back across the level: reversal side>0 wants close >
    level, side<0 wants close < level. Prefix-only read."""
    for j in range(touch_i + 1, min(touch_i + 1 + deadline, len(bars))):
        c = bars[j]["close"]
        if (c > level) if side > 0 else (c < level):
            return j
    return None


def void_edge(touch, d, side):
    """Fresh gap created by the displacement bar itself (protocol S3):
    long (side>0): d.low > touch.high, near edge = d.low.
    short: d.high < touch.low, near edge = d.high. None if no jump."""
    if side > 0:
        return d["low"] if d["low"] > touch["high"] else None
    return d["high"] if d["high"] < touch["low"] else None


def retrace_fill_idx(bars, edge, side, deadline=DEADLINE):
    """First bar in `bars` (list of candidates AFTER the void stamp)
    that retraces into the void from the trade's side with unambiguous
    open-precondition ordering: long starts at/above edge and pierces
    down; short starts at/below edge and pierces up. Index within
    `bars`, or None. Prefix-only read."""
    for j, b in enumerate(bars[:deadline]):
        if side > 0:
            if b["open"] >= edge and b["low"] <= edge:
                return j
        else:
            if b["open"] <= edge and b["high"] >= edge:
                return j
    return None


def opposing_liquidity(bars, touch_i, side, lookback=LIQ_LOOKBACK):
    """Extreme of the `lookback` completed bars STRICTLY BEFORE the
    touch bar: lowest low for a long (price falls toward it), highest
    high for a short. Returns None near series start."""
    lo = max(0, touch_i - lookback)
    seg = bars[lo:touch_i]
    if not seg:
        return None
    return min(b["low"] for b in seg) if side > 0 \
        else max(b["high"] for b in seg)


def variable_target(side, entry, risk, liquidity):
    """Protocol S4: nearer of 2R and the liquidity level; SKIP if the
    liquidity level is farther than 2R or absent. Returns a dict:
      {"skip": True} | {"skip": False, "target": px,
                        "bound_by_liquidity": bool}"""
    if liquidity is None:
        return {"skip": True}
    dist = (entry - liquidity) if side > 0 else (liquidity - entry)
    if dist > 2.0 * risk:                      # unreachable within 2R
        return {"skip": True}
    fixed = entry - 2.0 * risk if side > 0 else entry + 2.0 * risk
    nearer_is_liq = (liquidity > fixed) if side > 0 else (liquidity < fixed)
    return {"skip": False,
            "target": liquidity if nearer_is_liq else fixed,
            "bound_by_liquidity": bool(nearer_is_liq)}


# ---------------------------------------------------------------- study
def load_bars_and_events(market, imap):
    """Same decode + generator path as c2_local_study.study_market."""
    rows = dld.session_rows(market, session_days=None,
                            instrument_map=imap)
    rows = [r for r in rows
            if dld.trade_date_of(dld.ts_to_et(r["ts_event_ns"]))
            >= DEV_START]
    rows.sort(key=lambda r: r["ts_event_ns"])
    bars, mixed = dld.build_bars_30m(rows)
    rolls = dld.detect_rolls(rows)
    del rows
    from event_generators import OvernightLevelTouchV1
    gen = OvernightLevelTouchV1(tick_size=TICK[market], atr_period=14,
                                atr_floor_ticks=10, entry_style="level")
    events = []
    pending = list(rolls)
    for bar in bars:
        first_min_ns = int((bar["et"] - timedelta(minutes=30))
                           .replace(tzinfo=dld.ET).timestamp() * 1e9)
        while (pending and bar["symbol"] == pending[0]["new_symbol"]
               and pending[0]["ts_event_ns"] >= first_min_ns
               - 1_000_000_000):
            r = pending.pop(0)
            gen.on_rollover(bar["et"], r["old_symbol"], r["new_symbol"])
            break
        for ev in gen.on_bar({"open": bar["open"], "high": bar["high"],
                              "low": bar["low"], "close": bar["close"],
                              "et": bar["et"]}):
            events.append(ev)
    return bars, events


def _payoff_pair(bars, stamp_i, side, entry, atr):
    """Ladder-frame arms on the 4 completed bars strictly after the
    stamp (protocol S2/S3; touch/stamp-bar exclusion convention)."""
    win = bars[stamp_i + 1: stamp_i + 1 + WINDOW_BARS]
    rev = resolve_arm(win, side, entry, atr)
    cont = resolve_arm(win, -side, entry, atr)
    return rev, cont


def study_market(market, imap, committed):
    bars, events = load_bars_and_events(market, imap)
    bar_at = {b["et"]: i for i, b in enumerate(bars)}

    # -- soundness gate (a): replay reproduces committed event_et set
    repl_ets = {et.isoformat() for (et, *_r) in events}
    committed_ets = {e["event_et"] for e in committed}
    if repl_ets != committed_ets or len(events) != len(committed):
        raise SystemExit(
            f"SOUNDNESS(a) FAIL {market}: replayed {len(events)} events "
            f"vs committed {len(committed)}; set-equal="
            f"{repl_ets == committed_ets}")

    comm_by_key = {(e["event_et"], e["level_kind"]): e for e in committed}
    if len(comm_by_key) != len(committed):
        raise SystemExit(f"SOUNDNESS(a) FAIL {market}: committed ledger "
                         "has duplicate (event_et, level_kind) keys")
    rungs = {1: [], 2: [], 3: [], 4: []}
    rung5 = {"variable": [], "fixed": []}
    drop = {"no_disp": 0, "no_void": 0, "no_retrace": 0,
            "liq_missing_skip": 0, "liq_beyond_2r_skip": 0,
            "liq_bound_below_2r": 0}

    n1_exact = 0
    for (et, side, level, atr, ctx) in events:
        i0 = bar_at[et]
        ev_c = comm_by_key[(et.isoformat(), ctx["level_kind"])]
        # -- soundness gate (b): rung 1 reproduces committed contrast_R
        rev1, cont1 = _payoff_pair(bars, i0, side, level, atr)
        if abs((rev1 - cont1) - ev_c["contrast_R"]) > 1e-12:
            raise SystemExit(
                f"SOUNDNESS(b) FAIL {market} at {et}: contrast "
                f"{rev1 - cont1} != committed {ev_c['contrast_R']}")
        n1_exact += 1
        rungs[1].append({
            "et": et.isoformat(), "session_date": ctx["session_date"],
            "side": side, "level": level, "atr": atr, "i0": i0,
            "contrast_R": rev1 - cont1,
            "contrast_tc_R": _contrast_at(bars, i0, side,
                                          ctx["touch_bar_close"], atr),
            "fwd_R": ev_c["fwd_R"]})
        d = displacement_idx(bars, i0, side, level)
        if d is None:
            drop["no_disp"] += 1
            continue
        rev2, cont2 = _payoff_pair(bars, d, side, level, atr)
        r2 = {"et": et.isoformat(), "session_date": ctx["session_date"],
              "side": side, "level": level, "atr": atr, "i0": i0, "d": d,
              "contrast_R": rev2 - cont2,
              "contrast_tc_R": _contrast_at(bars, d, side,
                                            ctx["touch_bar_close"], atr),
              "fwd_R": ev_c["fwd_R"]}
        rungs[2].append(r2)
        touch = bars[i0]
        edge = void_edge(touch, bars[d], side)
        if edge is None:
            drop["no_void"] += 1
            continue
        rungs[3].append(dict(r2))            # same frame; gated subset
        r = retrace_fill_idx(bars[d + 1:], edge)
        if r is None:
            drop["no_retrace"] += 1
            continue
        fill_i = d + 1 + r
        rev4, cont4 = _payoff_pair(bars, fill_i, side, edge, atr)
        rungs[4].append({**r2, "fill_i": fill_i, "edge": edge,
                         "contrast_R": rev4 - cont4,
                         "contrast_tc_R": _contrast_at(
                             bars, fill_i, side,
                             bars[fill_i]["close"], atr)})
        # ---- rung 5: structural risk, variable target + skip filter
        stop = ((touch["low"] - STRUCT_BUFFER * atr) if side > 0
                else (touch["high"] + STRUCT_BUFFER * atr))
        risk = max(abs(edge - stop), RISK_FLOOR * atr)
        liq = opposing_liquidity(bars, i0, side)
        vt = variable_target(side, edge, risk, liq)
        if vt["skip"]:
            if liq is None:
                drop["liq_missing_skip"] += 1
            else:
                drop["liq_beyond_2r_skip"] += 1
        else:
            if vt["bound_by_liquidity"]:
                drop["liq_bound_below_2r"] += 1
            win = bars[fill_i + 1: fill_i + 1 + WINDOW_BARS]
            t_R_var = abs(vt["target"] - edge) / risk
            var_pay = resolve_arm(win, side, edge, risk, t_R=t_R_var,
                                  s_R=1.0)
            fix_pay = resolve_arm(win, side, edge, risk, t_R=2.0, s_R=1.0)
            rung5["variable"].append({"session_date": ctx["session_date"],
                                      "pay_R_STRUCT": var_pay,
                                      "pay_points": var_pay * risk})
            rung5["fixed"].append({"session_date": ctx["session_date"],
                                   "pay_R_STRUCT": fix_pay,
                                   "pay_points": fix_pay * risk})
    return {"bars": len(bars), "rungs": rungs, "drop": drop,
            "rung5": rung5, "n1_exact": n1_exact}


def _contrast_at(bars, stamp_i, side, entry, atr):
    win = bars[stamp_i + 1: stamp_i + 1 + WINDOW_BARS]
    return (resolve_arm(win, side, entry, atr)
            - resolve_arm(win, -side, entry, atr))


def cell_stats(rows, label, metric="contrast_R"):
    vals = [r[metric] for r in rows]
    sess = [r["session_date"] for r in rows]
    out = {"n": len(rows),
           "sessions": len(set(sess)),
           "event_mean": float(np.mean(vals)) if vals else None}
    if len(set(sess)) < len(vals) and len(vals) >= 30:
        est = clustered_ci(vals, sess, _rng(label))
        out["cluster_mean"], out["ci_low"], out["ci_high"] = est
    else:
        out["cluster_mean"] = out["ci_low"] = out["ci_high"] = None
        if len(vals) and len(set(sess)) >= len(vals):
            out["clustering_invalid"] = True
    return out


def main():
    imap = dld.load_instrument_map()
    led = json.load(open(LEDGER, encoding="utf-8"))
    results = {}
    for market in ("NQ", "GC"):
        print(f"replaying {market}...", flush=True)
        d = study_market(market, imap, led["events"][market])
        cells = {}
        for rung in (1, 2, 3, 4):
            rows = d["rungs"][rung]
            cells[f"rung{rung}"] = cell_stats(rows, f"{market}r{rung}")
            cells[f"rung{rung}_tc"] = cell_stats(rows, f"{market}r{rung}tc",
                                                 "contrast_tc_R")
        r5 = {"n_skipped": d["drop"]["liq_beyond_2r_skip"]
              + d["drop"]["liq_missing_skip"],
              "liq_bound_below_2r_n": d["drop"]["liq_bound_below_2r"]}
        for arm in ("variable", "fixed"):
            rows = d["rung5"][arm]
            r5[arm] = {"n": len(rows),
                       "sessions": len({x['session_date'] for x in rows})}
            if rows:
                vals = [x["pay_R_STRUCT"] for x in rows]
                sess = [x["session_date"] for x in rows]
                pts = [x["pay_points"] for x in rows]
                r5[arm]["event_mean_R_STRUCT"] = float(np.mean(vals))
                r5[arm]["event_mean_points"] = float(np.mean(pts))
                if len(set(sess)) < len(vals) and len(vals) >= 30:
                    r5[arm]["cluster_mean"], r5[arm]["ci_low"], \
                        r5[arm]["ci_high"] = clustered_ci(
                            vals, sess, _rng(f"{market}r5{arm}"))
        # paired difference variable - fixed, session-clustered
        v_rows, f_rows = d["rung5"]["variable"], d["rung5"]["fixed"]
        if v_rows:
            gv, gf = {}, {}
            for src, g in ((v_rows, gv), (f_rows, gf)):
                for x in src:
                    g.setdefault(x["session_date"], []).append(
                        x["pay_R_STRUCT"])
            shared = sorted(set(gv) & set(gf))
            rng = _rng(f"{market}r5diff")
            idx_v = {s: gv[s] for s in shared}
            idx_f = {s: gf[s] for s in shared}
            point = float(np.mean([np.mean(idx_v[s]) for s in shared])
                          - np.mean([np.mean(idx_f[s]) for s in shared]))
            boot = []
            for _ in range(399):
                pick = rng.integers(0, len(shared), size=len(shared))
                sel = [shared[i] for i in pick]
                boot.append(
                    np.mean([np.mean(idx_v[s]) for s in sel])
                    - np.mean([np.mean(idx_f[s]) for s in sel]))
            r5["diff_variable_minus_fixed"] = {
                "point": point,
                "ci": [float(np.quantile(boot, 0.025, method="lower")),
                       float(np.quantile(boot, 0.975, method="lower"))],
                "n_sessions": len(shared)}
        d["cells"] = cells
        d["rung5"] = r5
        results[market] = d

    json.dump(results, open(OUT, "w", encoding="utf-8"), default=float)

    # ---------------- report, funnel-first -----------------------------
    lines = ["ERL->IRL GATE-ABLATION (exploratory; protocol "
             "ERLIRL_ABLATION_PROTOCOL.md frozen first)", ""]
    kill_flips = []
    for market in ("NQ", "GC"):
        d = results[market]
        lines.append(f"== {market}  (bars {d['bars']}, "
                     f"sounds gates: replay-exact + rung-1 byte-exact)")
        lines.append(f"  drop funnel: {d['drop']}")
        for rung in (1, 2, 3, 4):
            c = d["cells"][f"rung{rung}"]
            if c["cluster_mean"] is None:
                lines.append(f"  rung{rung}: n={c['n']} sessions={c['sessions']}"
                             " (too few for CI)"
                             f" event-mean={c['event_mean']}")
                continue
            lines.append(
                f"  rung{rung}: n={c['n']} sessions={c['sessions']} "
                f"contrast cluster-mean={c['cluster_mean']:+.4f} "
                f"CI[{c['ci_low']:+.4f},{c['ci_high']:+.4f}] "
                f"(event-mean {c['event_mean']:+.4f}; tc "
                f"{d['cells'][f'rung{rung}_tc']['event_mean']:+.4f})")
            if c["n"] >= 100 and c["ci_low"] > 0.0 and rung >= 2:
                kill_flips.append(f"{market} rung{rung}")
        r5 = d["rung5"]
        for arm in ("variable", "fixed"):
            a = r5[arm]
            lines.append(f"  rung5-{arm}: n={a['n']} sessions="
                         f"{a['sessions']} mean_R={a.get('event_mean_R_STRUCT')}"
                         f" mean_pts={a.get('event_mean_points')} "
                         f"CI[{a.get('ci_low')},{a.get('ci_high')}]")
        dv = r5.get("diff_variable_minus_fixed")
        if dv:
            lines.append(f"  rung5 diff var-fixed={dv['point']:+.4f} "
                         f"CI[{dv['ci'][0]:+.4f},{dv['ci'][1]:+.4f}] "
                         f"(sessions {dv['n_sessions']})")
            if dv["n_sessions"] >= 100 and dv["ci"][0] > 0.0:
                kill_flips.append(f"{market} rung5")
        lines.append("")
    verdict = "FLIP" if kill_flips else "DEAD"
    lines.append(f"VERDICT (protocol S6, frozen pre-results): {verdict}"
                 + (f" — {kill_flips}; screening caution S6 applies"
                    if kill_flips else
                    " — no rung flips on either market; hypothesis "
                    "recorded dead on its own gates; no prereg"))
    text = "\n".join(lines) + "\n"
    open(REPORT, "w", encoding="utf-8").write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
