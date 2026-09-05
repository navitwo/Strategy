"""C2-RESIDUE-STOPWIDEN — offline upper-bound probe (see
C2_RESIDUE_STOPWIDEN_PROTOCOL.md for the frozen rule committed BEFORE this
code ran and before any result existed).

Does GC's overnight-high continuation effect survive a wider stop? Uses
ONLY fields already committed in c2_local_study.json (mfe_R/mae_R window
extremes on the reversal-arm signed 120m path, fwd_R horizon closes,
stored contrast_R). No decode, no Databento, no cloud. Read-only over
the ledger; writes c2_residue_stopwiden.json.

Method and its limit (protocol Limits — binding):
  Payoffs at barriers (stop s, target t; R units, 1R = 1 ATR) are
  resolved from WINDOW EXTREMES with NO first-touch ordering:
    rev : pess = -s if mae<=-s else (t if mfe>=t else 0)
          opt  =  t if mfe>=t else (-s if mae<=-s else 0)
    cont: trades the opposite side at the same barriers; its favorable
          extreme is -mae, adverse is -mfe:
          pess = -s if mfe>= s else (t if mae<=-t else 0)
          opt  =  t if mae<=-t else (-s if mfe>= s else 0)
  contrast(s) = rev - cont. Pessimistic and optimistic readings form a
  BRACKET that provably contains the bar-path truth (both arms' payoffs
  are monotone step functions of ordering; extreme-resolution gives each
  arm its worst/best possible value independently). This is the exact
  first-touch-blindness that invalidated the Campaign 1 screen:
  favourable numbers here are UPPER BOUNDS, not evidence.
  Bias calibration: at the frozen grid (s=0.5, t=2.0) the pessimistic
  emulation equals the exact bar-path payoff EXCEPT when the 120m bar
  path hit stop before target — where the extreme view reports the same
  -s. The optimistic emulation equals the exact payoff except where the
  true ordering was stop-first. So the stored contrast_R distribution
  must lie INSIDE the [pess, opt] bracket pointwise on averages;
  `baseline_gap` reports pess-vs-stored and opt-vs-stored gaps directly.

  Barrier grid exists only where extremes exist (120m window). The
  30/60/120/240m rows are the TIME-EXIT analogue: contrast_close(h) =
  2 * fwd_R(h) (the two arms close at +/-fwd_R) — stop-blind by
  construction; the hold-vs-stop interaction cannot be fully separated
  without a first-touch grid on bar paths (successor data, not this).

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


def arm_payoffs(mfe, mae, s, t):
    """(rev_pess, rev_opt, cont_pess, cont_opt) from window extremes."""
    rev_pess = -s if mae <= -s else (t if mfe >= t else 0.0)
    rev_opt = t if mfe >= t else (-s if mae <= -s else 0.0)
    cont_pess = -s if mfe >= s else (t if mae <= -t else 0.0)
    cont_opt = t if mae <= -t else (-s if mfe >= s else 0.0)
    return rev_pess, rev_opt, cont_pess, cont_opt


def _boot(vals, sess, tag):
    r = AA.eventmean_clusterboot(vals, sess, tag)
    lo, hi = r["ci95_R"]
    return {"point_R": round(r["point_R"], 4),
            "ci95_R": [round(lo, 4), round(hi, 4)]}


def cell(rows, s, t, name):
    sess = [e["session_date"] for e in rows]
    resolved = [arm_payoffs(e["mfe_R"], e["mae_R"], s, t) for e in rows]
    cp = [a - c for (a, _, c, _) in resolved]
    co = [b - d for (_, b, _, d) in resolved]
    pess = _boot(cp, sess, f"{SEED_TAG}:{name}:pess")
    opt = _boot(co, sess, f"{SEED_TAG}:{name}:opt")
    amb = float(np.mean([rp != ro for rp, ro, _, _ in resolved]
                        + [cp_ != op_ for *_, cp_, op_ in resolved]))
    out = {"n": len(rows), "stop_R": s, "target_R": t,
           "pess": pess, "opt": opt,
           "ambiguity_share_ordering_matters": round(amb, 4)}

    def scales(cel):
        c = cel["point_R"]
        return {"per_R": round(c / s, 4),
                "margin_per_R": round((abs(c) - FRICTION_RBASE) / s, 4)
                if c < 0 else None,
                "clears_friction_point": bool(c < -FRICTION_RBASE),
                "clears_friction_CI_wholly": bool(cel["ci95_R"][1]
                                                  < -FRICTION_RBASE)}
    out["scales_pess"] = scales(pess)
    out["scales_opt"] = scales(opt)
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
            "clears_friction_point": bool(pt < -FRICTION_RBASE),
            "clears_friction_CI_wholly": bool(r["ci95_R"][1]
                                              < -FRICTION_RBASE)}


def decide(gc_a: dict) -> str:
    """Frozen protocol rule on family A, GC overnight_high.
    Conservative reading wins; ties go to the more cautious branch."""
    tol = 0.01
    c05 = gc_a["0.5"]["pess"]["point_R"]
    c05o = gc_a["0.5"]["opt"]["point_R"]
    c10p = gc_a["1.0"]["pess"]["point_R"]
    c10o = gc_a["1.0"]["opt"]["point_R"]
    p15 = gc_a["1.5"]["pess"]["point_R"]
    p20 = gc_a["2.0"]["pess"]["point_R"]
    # DEAD if even the OPTIMISTIC bracket decays toward zero or inverts
    # at 1.0 (truth necessarily decays too), or pessimistic inverts at
    # 1.5/2.0 (a bound inverting the wrong way can still be blindness,
    # but inversion of the pess reading is not blindness-favourable).
    if c10o > min(c05o, c05) + tol:
        return "DEAD"
    if p15 > tol or p20 > tol:
        return "DEAD"
    # VIABLE-BOUND: pessimistic at 1.0 holds (does not decay toward zero),
    # no pessimistic inversion at 1.5/2.0, and some family-A cell has
    # CI wholly beyond the friction line (either bracket side counts,
    # flagged which).
    holds = c10p <= c05 + tol
    clears = any(gc_a[str(s)][side]["clears_friction_CI_wholly"]
                 for s in STOPS for side in ("pess", "opt"))
    if holds and clears:
        return "VIABLE-BOUND"
    return "INCONCLUSIVE"


def main():
    led = json.load(open(LEDGER, encoding="utf-8"))
    out = {"protocol_doc": "C2_RESIDUE_STOPWIDEN_PROTOCOL.md",
           "status": "EXPLORATORY-ONLY upper-bound probe; zero promotion power",
           "friction_R_base": FRICTION_RBASE, "stops_R": list(STOPS),
           "note": "1R = 1 ATR; contrasts in ATR points; margins per unit risked",
           "markets": {}}
    for mkt in ("GC", "NQ"):
        ev = led["events"][mkt]
        high = [e for e in ev if e["level_kind"] == "overnight_high"]
        fam_a = {str(s): cell(high, s, 2.0, f"{mkt}A{s}") for s in STOPS}
        fam_b = {str(s): cell(high, s, 2.0 * s, f"{mkt}B{s}") for s in STOPS}
        # baseline bias diagnostic vs the stored EXACT bar-path contrast
        stored = float(np.mean([e["contrast_R"] for e in high]))
        out["markets"][mkt] = {
            "overnight_high_n": len(high),
            "stored_exact_contrast_mean_R": round(stored, 4),
            "family_A_target_2R_fixed": fam_a,
            "family_B_target_2x_stop": fam_b,
            "time_exit_contrast_by_horizon": {
                str(h): time_exit(high, h, mkt) for h in HORIZONS},
        }
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
