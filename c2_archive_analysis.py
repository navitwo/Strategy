"""C2-ONLT-v1 archival analysis — offline recomputation from the committed ledger.

Every number in the C2 archive document is reproducible by THIS script alone
from ``c2_local_study.json`` (the committed per-event ledger). Read-only over
the artifact; writes only ``c2_archive_analysis.json``. No cloud, no
Databento access, no decode re-run.

Estimator conventions (both declared, neither hidden):
  PRIMARY/SENSITIVITY rows (section A): study-identical — import
  ``c2_local_study.clustered_ci`` (point = mean of session-cluster means,
  CI = cluster-resampled percentiles, method="lower", BOOT draws, seed tag
  ``SEED + market`` exactly as the study ran it). A self-check re-derives
  each committed primary CI bit-for-bit before anything else runs.
  HORIZON / TOUCH-PROFILE rows (sections B, C): point = EVENT MEAN (each
  event counts once — the natural population statistic for a descriptive
  profile); CI = session-clustered bootstrap RECOMPUTING the event mean on
  each draw (resample whole session clusters with replacement). A
  mean-of-cluster-means point against an event-weighted CI would mix two
  estimands; here point and CI share one estimator in both conventions.
  Seed tags are explicit per comparison: ``SEED + market + ":" + name``.

Sections B and C are EXPLORATORY — comparisons made after seeing the DEV
data; leads, not findings; zero promotion power under the frozen protocol.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

import numpy as np

import c2_local_study as S

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "c2_local_study.json")
OUT = os.path.join(HERE, "c2_archive_analysis.json")

HORIZONS = S.HORIZONS          # (30, 60, 120, 240) — frozen transport set
# Exploratory sections B/C use 4000 draws (stability for a descriptive
# profile; the study's 399-draw setting is reserved for the verdict CI and
# is what section A imports bit-for-bit). A borderline cell (GC 60m) is
# seed-swept below and labelled as such rather than reported as robust.
BOOT_EXPL = 4000


def study_estimator(values, sessions, seed_tag):
    """The study's own clustered_ci under an explicit seed tag."""
    rng = np.random.default_rng(S._seed_int(seed_tag))
    est = S.clustered_ci(values, sessions, rng)
    if est is None:
        return None
    point, lo, hi = est
    return {"point_R": point, "ci95_R": [lo, hi]}


def eventmean_clusterboot(values, sessions, seed_tag):
    """Event-mean point; session-cluster bootstrap of the event mean."""
    rng = np.random.default_rng(S._seed_int(seed_tag))
    v = np.asarray(values, dtype=float)
    sums, cnts = {}, {}
    for val, s in zip(v, sessions):
        sums[s] = sums.get(s, 0.0) + val
        cnts[s] = cnts.get(s, 0) + 1
    keys = sorted(sums)
    sa = np.array([sums[k] for k in keys])
    ca = np.array([cnts[k] for k in keys], dtype=float)
    point = float(v.sum() / len(v))
    pick = rng.integers(0, len(keys), size=(BOOT_EXPL, len(keys)))
    ds = sa[pick].sum(axis=1)
    dc = ca[pick].sum(axis=1)
    with np.errstate(invalid="ignore"):
        draws = np.where(dc > 0, ds / np.where(dc == 0, 1, dc), np.nan)
    draws = draws[~np.isnan(draws)]
    return {"point_R": point,
            "ci95_R": [float(np.percentile(draws, 2.5)),
                       float(np.percentile(draws, 97.5))]}


def _annotate(res, n, sessions, sign_note):
    if res is None:
        return {"n": n, "error": "clusters<2"}
    lo, hi = res["ci95_R"]
    sig = bool(lo > 0 or hi < 0)
    direction = "ns" if not sig else (
        "reversal" if res["point_R"] > 0 else "continuation")
    return {"n": n, "sessions": len(set(sessions)),
            "point_R": round(res["point_R"], 4),
            "ci95_R": [round(lo, 4), round(hi, 4)],
            "significant": sig, "direction": direction,
            "sign_convention": sign_note}


def seed_sweep(values, sessions, base_tag, n_seeds=25):
    """Share of seeds for which the clustered-bootstrap CI excludes zero.
    Honest labelling for borderline cells: a cell that flips across seeds
    is not a stable lead however the headline seed lands."""
    hits = 0
    for i in range(n_seeds):
        r = eventmean_clusterboot(values, sessions, f"{base_tag}#{i}")
        lo, hi = r["ci95_R"]
        if lo > 0 or hi < 0:
            hits += 1
    return hits / n_seeds


def main() -> dict:
    led = json.load(open(LEDGER, encoding="utf-8"))
    rep = led["report"]
    v = rep["verdicts"]
    prim_key = {"NQ": "primary_a_index", "GC": "primary_b_gold"}
    out = {"source_artifact": "c2_local_study.json",
           "theta_R": rep["theta_R"],
           "estimator_A": "c2_local_study.clustered_ci imported (study-identical)",
           "estimator_BC": "event-mean + session-cluster bootstrap of the "
                           "event-mean, %d draws" % S.BOOT,
           "exploratory_flag": "Sections B and C are post-hoc leads: made "
                               "after seeing DEV data, zero promotion power.",
           "markets": {}}

    CONTRAST_SIGN = "rev-cont barrier contrast: + = reversal, - = continuation"
    FWD_SIGN = "signed forward close return along reversal-arm: + = reversal, - = continuation"

    for mkt in ("NQ", "GC"):
        ev = led["events"][mkt]
        sess = [e["session_date"] for e in ev]

        # ---- A: confirmatory + sensitivities (study estimator) ----------
        committed = v[prim_key[mkt]]
        red = study_estimator([e["contrast_R"] for e in ev], sess,
                              S.SEED + mkt)
        assert abs(round(red["point_R"], 4) - round(committed["point_R"], 4)) \
            < 1e-9, f"{mkt}: primary point drifted"
        assert [round(c, 4) for c in red["ci95_R"]] == [
            round(committed["ci_low_R"], 4),
            round(committed["ci_high_R"], 4)], f"{mkt}: primary CI drifted"
        sens = {}
        for name, field in (("optimistic", "contrast_optimistic_R"),
                            ("touch_close", "contrast_touch_close_R")):
            r = study_estimator([e[field] for e in ev], sess,
                                S.SEED + mkt + ":" + name)
            sens[name] = _annotate(r, len(ev), sess, CONTRAST_SIGN)
        # headline descriptive event-means (committed values)
        em = {name: rep["primary_stats"][mkt][f"sensitivity_{name}_mean_R"]
              for name in ("optimistic", "touch_close")}

        # ---- B: horizon profile (event-mean + cluster-boot CI) ----------
        hp = {}
        for h in HORIZONS:
            pairs = [(e["fwd_R"][str(h)], e["session_date"]) for e in ev
                     if e["fwd_R"].get(str(h)) is not None]
            vals, ss = [p[0] for p in pairs], [p[1] for p in pairs]
            r = eventmean_clusterboot(vals, ss, S.SEED + f"{mkt}:eh{h}")
            cell = _annotate(r, len(pairs), ss, FWD_SIGN)
            cell["sig_seed_share_25"] = round(seed_sweep(
                vals, ss, S.SEED + f"{mkt}:eh{h}"), 3)
            hp[str(h)] = cell

        # ---- C: touch-direction split -----------------------------------
        by_level = defaultdict(list)
        for e in ev:
            by_level[e["level_kind"]].append(e)
        td = {}
        for kind, rows in sorted(by_level.items()):
            ksess = [r["session_date"] for r in rows]
            c = eventmean_clusterboot([r["contrast_R"] for r in rows], ksess,
                                      S.SEED + f"{mkt}:{kind}:contrast")
            pairs = [(r["fwd_R"]["120"], r["session_date"]) for r in rows
                     if r["fwd_R"].get("120") is not None]
            f = eventmean_clusterboot([p[0] for p in pairs],
                                      [p[1] for p in pairs],
                                      S.SEED + f"{mkt}:{kind}:fwd120")
            cell_c = _annotate(c, len(rows), ksess, CONTRAST_SIGN)
            cell_c["sig_seed_share_25"] = round(seed_sweep(
                [r["contrast_R"] for r in rows], ksess,
                S.SEED + f"{mkt}:{kind}:contrast"), 3)
            td[kind] = {
                "barrier_contrast": cell_c,
                "fwd_R_120m": _annotate(f, len(pairs),
                                        [p[1] for p in pairs], FWD_SIGN)}

        out["markets"][mkt] = {
            "primary_committed": committed,
            "primary_rederived_matches": True,
            "sensitivities_barrier_contrast": sens,
            "sensitivities_event_mean_R": em,
            "horizon_profile_signed_fwdR": hp,
            "touch_direction_split": td,
        }

    out["per_market_points_R"] = {
        m: rep["primary_stats"][m]["point_cluster_mean_R"] for m in ("NQ", "GC")}
    out["pooled_descriptive"] = rep["pooled_descriptive"]

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))
    print(f"\n[written] {OUT}")


if __name__ == "__main__":
    main()
