"""C2-ONLT-v1 local event-study pass — DEVELOPMENT DATA ONLY.

Frozen protocol C2-ONLT-v1 (CAMPAIGN2_OVERNIGHT_LEVEL_TOUCH_
PREREGISTRATION.md, 2026-09-04 amendments included), executed exactly as
registered on the guard-verified local Databento pipeline:

  population   NQ + GC, 2010-06-07 .. 2024-12-31 (DEV only; the
               date gate physically enforces the ceiling)
  generator    overnight_level_touch_v1, 30m ET bars, complete
               31-bar overnights only (fail-closed),
               c2_entry_style=level (primary), touch_close sensitivity
               reported separately,
               ATR floor 10 ticks with atr_floor_rejects published
  outcomes     T{0.5,1,1.5,2} x S{0.5,1,1.5,2} first-touch on signed
               forward paths; MFE/MAE; horizons 30/60/120/240 min
  primary      cell T2S0.5, horizon 120m, PAIRED contrast
               reversal - continuation, pessimistic (stop-first)
               ambiguity, per-arm payoff winsorized (-0.5, +2.0)
               -> contrast bounded [-2.5, +2.5]
  inference    session-date clustered bootstrap, fixed seed, 399
               resamples, two-sided 95% percentile CI (method=lower),
               theta = 0.2R NEVER widened; three-outcome geometry via
               campaign2_analysis.classify_primary
  verdicts     Primary A = NQ only, Primary B = GC only, computed and
               reported SEPARATELY, never pooled; pooled equal-market
               contrast is descriptive only; screening statistic
               (screen_vs_zero) reported, zero promotion power
  gates        each verdict needs achieved n >= 800 (frozen central
               minimum-passing-n); realized contrast dispersion is
               reported against the anchored 1.6015R central value;
               if n < 800 or dispersion materially exceeds the anchor,
               the run STANDS DOWN and reports instead of classifying.

Touch-bar exclusion: the frozen rule excludes the touch bar from
post-event MFE/MAE and first-touch resolution, so resolution starts at
the NEXT completed bar and the 120-minute window spans the four bars
after the touch bar.

No optimization, no parameter selection, no second look: ONE pass, the
frozen level-primary population (the event set is entry-style
independent), resolving the primary T2S0.5/120m/pessimistic contrast
for the verdict and the PREREGISTERED declared sensitivities
(optimistic target-first; touch-bar-close entry) as REPORTED event
means only — never classified, never promoted. Nothing else is
computed.

Output: c2_local_study.json (events, funnel, per-verdict statistics)
plus a printed funnel-first report. Run:
    python c2_local_study.py
"""
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta

import numpy as np

import databento_local_data as dld
from campaign2_analysis import (CONTRAST_WINSOR_R, PRIMARY_CELL,
                                PRIMARY_HORIZON_MIN, THETA_R,
                                classify_primary, screen_vs_zero,
                                verdict_pack)
from event_generators import OvernightLevelTouchV1

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "c2_local_study.json")

DEV_START = date(2010, 6, 7)
DEV_END = dld.DEV_END                    # 2024-12-31, the gate itself
TICK = {"NQ": 0.25, "GC": 0.10}
HORIZONS = (30, 60, 120, 240)
BOOT = 399
SEED = "C2-ONLT-v1-local-pass-1"
# the four primary-decision quantities per prereg 5, frozen:
T_R, S_R = 2.0, 0.5


def _seed_int(text):
    return int(hashlib.sha256(text.encode()).hexdigest()[:16], 16)


def resolve_arm(path_bars, side, entry_px, risk_dist,
                t_R=T_R, s_R=S_R, pessimistic=True):
    """First-touch of +t_R*risk / -s_R*risk on the signed path over the
    post-touch bars. Returns payoff in R units: +t_R target-first,
    -s_R stop-first, 0 if undecided within the window (bounded by
    construction inside (-s_R, +t_R)). Same-bar ambiguity resolves
    stop-first when pessimistic, target-first otherwise (prereg 4:
    pessimistic primary, optimistic declared sensitivity)."""
    rd = max(risk_dist, 1e-12)
    for b in path_bars:
        fav = ((b["high"] - entry_px) if side > 0
               else (entry_px - b["low"])) / rd
        adv = ((entry_px - b["low"]) if side > 0
               else (b["high"] - entry_px)) / rd
        hit_t, hit_s = fav >= t_R, adv <= -s_R
        if hit_t and hit_s:
            return -s_R if pessimistic else t_R
        if hit_s:
            return -s_R
        if hit_t:
            return t_R
    return 0.0


def horizon_ret_r(path_bars, touch_et, side, entry_px, risk_dist,
                  horizon_min):
    """Signed forward R at a fixed horizon: the first DELIVERED bar whose
    elapsed time from the TOUCH BAR >= horizon closes it — identical
    convention to the hosted _advance_events/_elapsed_min loop
    ((agg.ts - ev.ts0)/60 >= h, gaps included). None when the stream
    ends before the horizon."""
    for b in path_bars:
        elapsed = (b["et"] - touch_et).total_seconds() / 60.0
        if elapsed >= horizon_min:
            rd = max(risk_dist, 1e-12)
            return ((b["close"] - entry_px) / rd) * side
    return None


def study_market(market, imap):
    """Decode the gated dev stream once per market; run the frozen
    generator; resolve primary-arm payoffs inline (bounded memory).

    Goes through dld.session_rows — the sanctioned research-facing
    accessor — never the raw decode primitive (the date-gate
    self-audit enforces exactly this routing).
    """
    rows = dld.session_rows(market, session_days=None,
                            instrument_map=imap)
    rows = [r for r in rows
            if dld.trade_date_of(
                dld.ts_to_et(r["ts_event_ns"])) >= DEV_START]
    rows.sort(key=lambda r: r["ts_event_ns"])
    bars, mixed = dld.build_bars_30m(rows)
    rolls = dld.detect_rolls(rows)
    del rows                                # free the minute rows

    gen = OvernightLevelTouchV1(tick_size=TICK[market], atr_period=14,
                                atr_floor_ticks=10,
                                entry_style="level")
    events = []
    pending = list(rolls)
    for bar in bars:
        first_min_ns = int((bar["et"] - timedelta(minutes=30)
                            ).replace(tzinfo=dld.ET).timestamp() * 1e9)
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

    # index bars by end time for post-touch path slicing
    bar_at = {b["et"]: i for i, b in enumerate(bars)}
    out = []
    for (et, side, level, atr, ctx) in events:
        i0 = bar_at[et]
        horizon_bars = bars[i0 + 1: i0 + 1 + (PRIMARY_HORIZON_MIN // 30)]
        path8 = bars[i0 + 1: i0 + 1 + 8]          # covers the 240m horizon
        rev = resolve_arm(horizon_bars, side, level, atr)
        cont = resolve_arm(horizon_bars, -side, level, atr)
        contrast = rev - cont
        # declared sensitivity (prereg 4): optimistic target-first on
        # same-bar ambiguity -- reported, never a verdict
        rev_opt = resolve_arm(horizon_bars, side, level, atr,
                              pessimistic=False)
        cont_opt = resolve_arm(horizon_bars, -side, level, atr,
                               pessimistic=False)
        # declared sensitivity (Amendment 4): touch-bar-close entry,
        # identical levels/risk/timing/ambiguity -- reported, not this
        # pass's primary
        tc = ctx["touch_bar_close"]
        rev_tc = resolve_arm(horizon_bars, side, tc, atr)
        cont_tc = resolve_arm(horizon_bars, -side, tc, atr)
        # transport (prereg 4): signed forward R at 30/60/120/240 and
        # MFE/MAE on the reversal arm's signed path
        fwd = {str(h): horizon_ret_r(path8, et, side, level, atr, h)
               for h in HORIZONS}
        mfe = mae = 0.0
        rd = max(atr, 1e-12)
        for b in horizon_bars:
            fav = ((b["high"] - level) if side > 0
                   else (level - b["low"])) / rd
            adv = ((level - b["low"]) if side > 0
                   else (b["high"] - level)) / rd
            mfe = max(mfe, fav)
            mae = min(mae, adv)
        out.append({
            "event_et": et.isoformat(),
            "session_date": ctx["session_date"],
            "level_kind": ctx["level_kind"],
            "roll_generation": ctx["roll_generation"],
            "atr_points": ctx["atr_points"],
            "reversal_R": rev, "continuation_R": cont,
            "contrast_R": contrast,
            "contrast_optimistic_R": rev_opt - cont_opt,
            "contrast_touch_close_R": rev_tc - cont_tc,
            "fwd_R": fwd, "mfe_R": round(mfe, 6), "mae_R": round(mae, 6),
        })
    return {"bars": len(bars), "mixed_slots": len(mixed),
            "rolls": len(rolls), "events": out,
            "atr_floor_rejects": gen.atr_floor_rejects}


def clustered_ci(contrasts, sessions, rng, boot=BOOT):
    """Session-date clustered bootstrap of the mean paired contrast
    (prereg 4/5: clusters = session dates, resample clusters, two-sided
    95% percentile CI, method=lower). Returns (point, ci_low, ci_high)
    where point is the MEAN OF CLUSTER MEANS — the point and the CI
    come from the identical estimator (an event-weighted point against
    a cluster-resampled CI would be two different estimands; caught in
    self-review 2026-09-04)."""
    uniq = sorted(set(sessions))
    idx_by_session = {s: [i for i, ss in enumerate(sessions) if ss == s]
                      for s in uniq}
    means = np.array([float(np.mean([contrasts[i] for i in idx_by_session[s]]))
                      for s in uniq])
    if len(uniq) < 2:
        return None
    point = float(means.mean())
    idx = rng.integers(0, len(uniq), size=(boot, len(uniq)))
    boots = means[idx].mean(axis=1)
    return (point,
            float(np.quantile(boots, 0.025, method="lower")),
            float(np.quantile(boots, 0.975, method="lower")))


def main():
    rng = np.random.default_rng(_seed_int(SEED))
    imap = dld.load_instrument_map()
    per_market = {}
    for market in ("NQ", "GC"):
        print(f"decoding {market} dev stream (this is the slow part)...",
              flush=True)
        per_market[market] = study_market(market, imap)

    # ---- funnel FIRST, per the directive ------------------------------
    funnel = {}
    stats = {}
    results_by_market = {}
    for market in ("NQ", "GC"):
        d = per_market[market]
        ev = d["events"]
        n = len(ev)
        sessions = sorted({e["session_date"] for e in ev})
        contrasts = [e["contrast_R"] for e in ev]
        event_mean = float(np.mean(contrasts)) if n else 0.0
        sd = float(np.std(contrasts, ddof=1)) if n > 1 else 0.0
        est = clustered_ci(contrasts, [e["session_date"] for e in ev],
                           np.random.default_rng(_seed_int(SEED + market))) \
            if n else None
        funnel[market] = {
            "bars_30m": d["bars"], "mixed_slots": d["mixed_slots"],
            "rolls": d["rolls"], "events": n,
            "atr_floor_rejects": d["atr_floor_rejects"],
            "touch_candidates": n + d["atr_floor_rejects"],
            "retention": (n / (n + d["atr_floor_rejects"])
                          if n + d["atr_floor_rejects"] else None),
            "sessions": len(sessions),
        }
        stats[market] = {
            "n": n, "sessions": len(sessions),
            "point_cluster_mean_R": est[0] if est else None,
            "event_mean_R_descriptive": event_mean,
            "sd_contrast_R": sd,
            "ci95_R": list(est[1:]) if est else None,
            # declared sensitivities: event-means of the alternative
            # ambiguity convention and alternative entry convention.
            # Reported per prereg; NEVER verdicts, NEVER re-classified.
            "sensitivity_optimistic_mean_R": float(np.mean(
                [e["contrast_optimistic_R"] for e in ev])) if n else None,
            "sensitivity_touch_close_mean_R": float(np.mean(
                [e["contrast_touch_close_R"] for e in ev])) if n else None,
        }
        if est is not None:
            results_by_market[market] = {
                "point": est[0], "ci": est[1:], "n": n,
                "sessions": len(sessions)}

    # ---- stand-down checks BEFORE any classification ------------------
    # prereg 4: genuine session-date clustering requires sessions < n --
    # protocol-mandatory assertion, never merely reported.
    for m in ("NQ", "GC"):
        s = stats[m]
        assert s["sessions"] < s["n"], (
            f"{m}: clustered bootstrap invalid — sessions={s['sessions']} "
            f">= n={s['n']}; clusters are not observations")
    stand_down = []
    for m in ("NQ", "GC"):
        s = stats[m]
        if s["n"] < 800:
            stand_down.append(f"{m}: achieved n={s['n']} < frozen gate 800")
        if s["sd_contrast_R"] > 1.6015 * 1.5:
            stand_down.append(
                f"{m}: realized contrast sd={s['sd_contrast_R']:.4f}R "
                f"materially exceeds anchored central 1.6015R (>1.5x)")
    pack = verdict_pack(results_by_market) if results_by_market else {}

    # descriptive pooled equal-market contrast (never a verdict)
    pooled = {}
    if len(results_by_market) == 2:
        pooled["point_R"] = float(np.mean(
            [stats[m]["point_cluster_mean_R"] for m in ("NQ", "GC")]))
        pooled["label"] = "descriptive_only_never_a_verdict"

    report = {
        "protocol": "C2-ONLT-v1", "pass": "local-dev-only (1)",
        "seed": SEED, "dev_range": [DEV_START.isoformat(),
                                    DEV_END.isoformat()],
        "funnel": funnel,
        "primary_stats": stats,
        "anchored_central_sd_R": 1.6015,
        "frozen_gate_n": 800,
        "stand_down": stand_down,
        "verdicts": pack,
        "pooled_descriptive": pooled,
        "theta_R": THETA_R, "primary_cell": PRIMARY_CELL,
        "horizon_min": PRIMARY_HORIZON_MIN,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump({"report": report,
                   "events": {m: per_market[m]["events"]
                              for m in ("NQ", "GC")}}, fh)
    print(json.dumps(report, indent=1))
    if stand_down:
        print("\nSTAND DOWN — classify nothing:")
        for line in stand_down:
            print("  *", line)
    else:
        print("\nGate passed: verdicts below are the frozen labels.")


if __name__ == "__main__":
    main()
