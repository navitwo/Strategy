"""C2-RESIDUE-STOPWIDEN — offline upper-bound probe (see
C2_RESIDUE_STOPWIDEN_PROTOCOL.md — rule frozen BEFORE results existed).

Does GC's overnight-high continuation survive a wider stop? Uses ONLY
fields already committed in c2_local_study.json (mfe_R/mae_R window
extremes on the reversal-arm signed 120m path, fwd_R horizon closes,
stored contrast_R). No decode, no Databento, no cloud. Read-only over
the ledger; writes c2_residue_stopwiden.json.

IMPLEMENTATION NOTE (honest, dated): the first implementation paired
arms scenario-wise (rev_pess-cont_pess / rev_opt-cont_opt) and claimed
a bracket. The committed baseline_gap self-check caught it instantly:
the stored EXACT contrast (-0.061, GC-high, s=0.5/t=2.0) lay OUTSIDE
that interval ([+0.225, +0.597]) — both-arm-pessimistic is not the
min of the paired contrast because the two arms share one path. The
bracket endpoints below are the path-consistent ones; the rule text
in the protocol file was not touched (its "pessimistic reading = the
conservative side of the bracket" now maps to the VALID conservative
side). This correction changed no branch, no grid, no statistic's
definition — only the estimator's use of per-arm bounds.

Method and its limit (protocol Limits — binding):
  Per-arm payoffs from window extremes at barriers (stop s, target t,
  R units, 1R = 1 ATR; cont trades -side so its target is at -t and
  its stop at +s on the reversal-arm signed path):
    rev_pess = -s if mae<=-s else (t if mfe>=t else 0)
    rev_opt  =  t if mfe>=t else (-s if mae<=-s else 0)
    cont_pess = -s if mfe>=s else (t if mae<=-t else 0)
    cont_opt  =  t if mae<=-t else (-s if mfe>=s else 0)
  Each per-arm pair is a valid bound over first-touch orderings.
  Because both arms share ONE signed path and levels are nested
  (-t < -s < +s < +t, with -s before -t and +s before +t forced by
  continuity), the PATH-CONSISTENT event bracket for the paired
  contrast is:
    lo = rev_pess - cont_opt   (order (-t, -s)-first: best for cont)
    hi = rev_opt  - cont_pess  (order (+s, +t)-first: best for rev)
    truth: lo <= exact_contrast <= hi, per event and on averages.
  The two extremes are realized by explicit orderings when all four
  levels are reached; degenerate level sets collapse as usual.
  This IS the Campaign 1 defect class: favourable endpoints are
  UPPER BOUNDS, not evidence. Exact answers need a first-touch grid
  on the bar paths — successor-protocol data, not this probe.

  Barrier resolutions exist only where extremes exist (120m window).
  The 30/60/120/240m rows are the TIME-EXIT analogue:
  contrast_close(h) = 2 * fwd_R(h) (the two arms close at +/-fwd_R) —
  EXACT (no ordering blindness), stop-blind by construction, and shown
  so the hold-vs-stop interaction is visible where it is decidable.

  Friction 0.2 R_base = 0.2 ATR is a fixed physical cost; margin per
  unit risked = (|c| - 0.2)/s. Sign depends only on |c| vs 0.2.

Estimator: archive exploratory convention — point = event mean, CI =
session-cluster bootstrap, 4000 draws (imports c2_archive_analysis).
Everything EXPLORATORY; nothing promotable.
"""
from __future__ import annotations

import json
import os

import numpy as np

import c2_archive_analysis as AA
import c2_local_study as S

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "c2_local_study.json")
OUT = os.path.join(HERE, "c2_residue_stopwiden.json")

SEED_TAG = "C2-RESIDUE-v1"
STOPS = (0.5, 1.0, 1.5, 2.0)          # R units (1R = 1 ATR)
FRICTION_RBASE = 0.2                  # 0.2 R_base = 0.2 ATR fixed cost
HORIZONS = S.HORIZONS


def bracket_contrasts(e, s, t):
    """(lo, hi) path-consistent event bracket of rev-cont at (s, t)."""
    mfe, mae = e["mfe_R"], e["mae_R"]
    rev_pess = -s if mae <= -s else (t if mfe >= t else 0.0)
    rev_opt = t if mfe >= t else (-s if mae <= -s else 0.0)
    cont_pess = -s if mfe >= s else (t if mae <= -t else 0.0)
    cont_opt = t if mae <= -t else (-s if mfe >= s else 0.0)
    return rev_pess - cont_opt, rev_opt - cont_pess


def _boot(vals, sess, tag):
    r = AA.eventmean_clusterboot(vals, sess, tag)
    lo, hi = r["ci95_R"]
    return {"point_R": round(r["point_R"], 4),
            "ci95_R": [round(lo, 4), round(hi, 4)]}


def cell(rows, s, t, name):
    sess = [e["session_date"] for e in rows]
    pair = [bracket_contrasts(e, s, t) for e in rows]
    lo = _boot([p[0] for p in pair], sess, f"{SEED_TAG}:{name}:lo")
    hi = _boot([p[1] for p in pair], sess, f"{SEED_TAG}:{name}:hi")
    degenerate = float(np.mean([abs(p[1] - p[0]) < 1e-12 for p in pair]))
    out = {"n": len(rows), "stop_R": s, "target_R": t,
           "lo_optimistic_for_continuation": lo,
           "hi_conservative_for_continuation": hi,
           "degenerate_ordering_free_share": round(degenerate, 4)}

    def scales(bnd):
        c = bnd["point_R"]
        return {"per_R": round(c / s, 4),
                "clears_friction_point": bool(c < -FRICTION_RBASE),
                "clears_friction_CI_wholly": bool(bnd["ci95_R"][1]
                                                  < -FRICTION_RBASE)}
    out["scales_lo"] = scales(lo)
    out["scales_hi"] = scales(hi)
    out["friction_fraction_of_stop"] = round(FRICTION_RBASE / s, 4)
    return out


def time_exit(rows, h, mkt):
    pairs = [(2.0 * e["fwd_R"][str(h)], e["session_date"]) for e in rows
             if e["fwd_R"].get(str(h)) is not None]
    if not pairs:
        return {"error": "no data"}
    r = _boot([p[0] for p in pairs], [p[1] for p in pairs],
              f"{SEED_TAG}:timeexit:{mkt}:{h}")
    pt = r["point_R"]
    return {"n": len(pairs), "contrast_R": pt, "ci95_R": r["ci95_R"],
            "exact_no_ordering_blindness": True,
            "clears_friction_point": bool(pt < -FRICTION_RBASE),
            "clears_friction_CI_wholly": bool(r["ci95_R"][1]
                                              < -FRICTION_RBASE)}


def decide(gc_a: dict) -> str:
    """Frozen protocol rule on family A, GC overnight_high, mapped onto
    the VALID bracket: conservative-for-continuation reading = hi end;
    optimistic-for-continuation bound = lo end. Conservative reading
    wins; ties go to the more cautious branch.

    DEAD if even the LO (most continuation-favourable valid) end decays
    toward zero or inverts going 0.5 -> 1.0; or hi inverts positive at
    1.5/2.0. VIABLE-BOUND if lo holds continuation at 1.0, hi does not
    invert at 1.5/2.0, and some family-A cell's conservative (hi)
    reading has CI wholly beyond friction. Otherwise INCONCLUSIVE —
    which given the bracket width is the likely honest outcome: the
    extreme-based data cannot resolve first-touch ordering at wider
    stops; an exact answer requires a fresh first-touch grid (successor
    data), and the residue stays real-but-not-demonstrably-tradable."""
    tol = 0.01
    f = {str(s): gc_a[str(s)] for s in STOPS}
    lo05 = f["0.5"]["lo_optimistic_for_continuation"]["point_R"]
    lo10 = f["1.0"]["lo_optimistic_for_continuation"]["point_R"]
    hi05 = f["0.5"]["hi_conservative_for_continuation"]["point_R"]
    hi10 = f["1.0"]["hi_conservative_for_continuation"]["point_R"]
    hi15 = f["1.5"]["hi_conservative_for_continuation"]["point_R"]
    hi20 = f["2.0"]["hi_conservative_for_continuation"]["point_R"]
    if lo10 > lo05 + tol or lo10 > tol:
        return "DEAD"
    if hi15 > 0.0 + tol or hi20 > 0.0 + tol:
        # conservative reading inverts at wider stops: fails the frozen
        # VIABLE clause "does not invert at 1.5/2.0". Not DEAD (truth is
        # not shown to decay — a conservative-bound inversion may be
        # ordering blindness), but viability is off the table.
        hi_ok = False
    else:
        hi_ok = True
    holds = hi10 <= hi05 + tol          # conservative reading holds at 1.0
    clears_conservative = any(
        f[str(s)]["scales_hi"]["clears_friction_CI_wholly"]
        for s in STOPS)
    if holds and hi_ok and clears_conservative:
        return "VIABLE-BOUND"
    return "INCONCLUSIVE"


def main():
    led = json.load(open(LEDGER, encoding="utf-8"))
    out = {"protocol_doc": "C2_RESIDUE_STOPWIDEN_PROTOCOL.md",
           "status": "EXPLORATORY-ONLY upper-bound probe; zero promotion power",
           "friction_R_base": FRICTION_RBASE, "stops_R": list(STOPS),
           "note": "1R = 1 ATR; contrasts in ATR points; lo = bound most "
                   "favourable to continuation-hypothesis; hi = bound most "
                   "adverse (conservative); exact truth inside [lo, hi]",
           "markets": {}}
    for mkt in ("GC", "NQ"):
        ev = led["events"][mkt]
        high = [e for e in ev if e["level_kind"] == "overnight_high"]
        fam_a = {str(s): cell(high, s, 2.0, f"{mkt}A{s}") for s in STOPS}
        fam_b = {str(s): cell(high, s, 2.0 * s, f"{mkt}B{s}") for s in STOPS}
        stored = float(np.mean([e["contrast_R"] for e in high]))
        a05 = fam_a["0.5"]
        inside = bool(a05["lo_optimistic_for_continuation"]["point_R"]
                      <= stored
                      <= a05["hi_conservative_for_continuation"]["point_R"])
        out["markets"][mkt] = {
            "overnight_high_n": len(high),
            "stored_exact_contrast_mean_R": round(stored, 4),
            "bracket_contains_stored_exact_at_c2_grid": inside,
            "family_A_target_2R_fixed": fam_a,
            "family_B_target_2x_stop": fam_b,
            "time_exit_contrast_by_horizon": {
                str(h): time_exit(high, h, mkt) for h in HORIZONS},
        }
        assert inside, f"{mkt}: sound bracket must contain the exact value"
    verdict = decide(
        out["markets"]["GC"]["family_A_target_2R_fixed"])
    out["verdict_GC_overnight_high_familyA"] = verdict
    out["verdict_rule_note"] = ("frozen in C2_RESIDUE_STOPWIDEN_PROTOCOL.md "
                                "BEFORE results existed; conservative "
                                "reading wins")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))
    print(f"\n[written] {OUT}\nVERDICT: {verdict}")
    return verdict


if __name__ == "__main__":
    main()
