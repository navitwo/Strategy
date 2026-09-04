"""Campaign-2 bounded primary estimator and empirically anchored feasibility grid.

PROTOCOL rule (2026-09-04): every input to a feasibility proof must be
empirically anchored to committed data, or declared as an assumption with a
reported sensitivity range. ``per_obs_sd_R`` therefore has no default: callers
must pass an anchored number (see ``ledger_contrast_dispersion``).
"""
import hashlib
import json
import os

import numpy as np

THETA_R = 0.2
PRIMARY_CELL = "T2S0.5"
PRIMARY_HORIZON_MIN = 120
# The simulated unit is the PAIRED contrast (reversal - continuation). Each
# arm's payoff is winsorized to [-0.5R, +2.0R] (prereg section 5), so the
# contrast is bounded [-2.5R, +2.5R]. Clipping contrast draws at the per-arm
# bounds instead silently truncates the left tail and biases the null mean
# upward (the original 0.45-sd cut had this bug; caught 2026-09-04).
CONTRAST_WINSOR_R = (-2.5, 2.5)
FEASIBILITY_GRID = (200, 400, 800, 1600, 3200)
FIRE_FLOOR = 0.80

OPERABILITY_SCENARIOS = {          # gate the result
    "reversal_positive": +0.55,
    "continuation_positive": -0.55,
    "null_equivalent": 0.0,
}
REPORTED_SCENARIOS = {             # published at every grid point, never gate
    "boundary_inconclusive": +THETA_R,
    "near_threshold_positive": 0.3,
}
SCENARIOS = {**OPERABILITY_SCENARIOS, **REPORTED_SCENARIOS}

# Anchors recomputed from the committed E19B-R FT ledgers on every test run.
LEDGER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "e19br_ft_ledger")


def ledger_contrast_dispersion(ledger_dir=LEDGER_DIR):
    """Contrast dispersion derived from the frozen 1,121-row FT32 ledgers.

    T2S0.5 pessimistic (same-bar ambiguity priced stop-first): per-arm payoff
    {target +2.0R, stop -0.5R, undecided 0}. Returns the per-arm stats over
    decided arms, the independence floor sqrt(2)*sd (arms run opposite
    directions on one path, so true variance is >= this), and the trimodal
    central value (contrast {+2.5,-2.5,0} at P(target-first) per tail).
    """
    cells = [(t, s) for t in (.5, 1, 1.5, 2) for s in (.5, 1, 1.5, 2)]
    idx = cells.index((2.0, 0.5))
    pay = {1: 2.0, 2: -0.5, 3: -0.5}
    decided = []
    n_target_first = 0
    n_rows = 0
    for instrument in ("NQ", "ES", "YM", "RTY"):
        path = os.path.join(ledger_dir, f"{instrument}_ft.jsonl")
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            code = json.loads(line)["codes"][idx]
            n_rows += 1
            if code == 1:
                n_target_first += 1
            if code:
                decided.append(pay[code])
    n = len(decided)
    mean = sum(decided) / n
    per_arm_sd = (sum((v - mean) ** 2 for v in decided) / (n - 1)) ** 0.5
    p_tail = n_target_first / n_rows
    trimodal = (2.0 * p_tail * 2.5 ** 2) ** 0.5
    return {"rows": n_rows, "decided_n": n, "decided_mean_R": mean,
            "per_arm_sd_R": per_arm_sd,
            "contrast_sd_independent_floor_R": 2 ** 0.5 * per_arm_sd,
            "p_target_first": p_tail,
            "contrast_sd_trimodal_central_R": trimodal}


def classify_primary(point, ci_low, ci_high, theta=THETA_R):
    """Frozen three-outcome interval geometry (prereg section 5).

    POSITIVE requires the complete CI strictly beyond +theta (reversal) or
    strictly below -theta (continuation, direction reported). NULL requires
    the complete CI strictly inside [-theta, +theta]. Every other geometry
    is INCONCLUSIVE. theta is fixed at 0.2R and is never widened.
    """
    if ci_low > theta or ci_high < -theta:
        return "POSITIVE"
    if ci_low > -theta and ci_high < theta:
        return "NULL"
    return "INCONCLUSIVE"


# Pre-data amendment (2026-09-04, prereg section 5): the primary splits into
# two verdicts computed SEPARATELY and never pooled -- a gold result cannot
# be diluted by an index null, and vice versa.
PRIMARY_VERDICTS = {
    "primary_a_index": ("NQ",),
    "primary_b_gold": ("GC",),
}
# Descriptive-only pooled replication (never a verdict).
POOLED_DESCRIPTIVE = ("NQ", "GC")


def screen_vs_zero(ci_low, ci_high, theta=THETA_R):
    """Screening statistic vs zero, reported alongside each primary verdict.

    Prereg section 5 (2026-09-04): descriptive only. A POSITIVE confirmatory
    verdict REQUIRES classify_primary on the same interval; this function can
    never promote anything -- its 'significant_not_tradable' label exists
    precisely to keep a real-but-below-theta effect from collapsing into an
    uninformative NULL while still marking it NOT tradable at theta.
    """
    excludes_zero = ci_low > 0.0 or ci_high < 0.0
    inside_theta = -theta <= ci_low and ci_high <= theta
    if not excludes_zero:
        return {"screening": "not_significant_vs_zero",
                "confirmatory_required": classify_primary(
                    (ci_low + ci_high) / 2.0, ci_low, ci_high, theta)}
    if inside_theta:
        return {"screening": "significant_not_tradable",
                "confirmatory_required": classify_primary(
                    (ci_low + ci_high) / 2.0, ci_low, ci_high, theta)}
    return {"screening": "significant_beyond_theta",
            "confirmatory_required": classify_primary(
                (ci_low + ci_high) / 2.0, ci_low, ci_high, theta)}


def verdict_pack(results_by_market, theta=THETA_R):
    """A/B verdict pack from per-market point/CI estimates.

    results_by_market: {market: {"point": float, "ci": (low, high)}} for the
    markets a verdict covers. NEVER pools: each verdict is evaluated on its
    own market's interval. The pooled equal-weight estimate, if supplied as
    a synthetic 'POOLED' key, is labeled descriptive and cannot carry a
    verdict.
    """
    pack = {}
    for verdict, markets in PRIMARY_VERDICTS.items():
        missing = [m for m in markets if m not in results_by_market]
        if missing:
            pack[verdict] = {"error": f"missing markets {missing}",
                             "operable": False}
            continue
        market = markets[0]  # both verdicts are single-market by design
        est = results_by_market[market]
        lo, hi = est["ci"]
        pack[verdict] = {
            "market": market, "n": est.get("n"), "sessions": est.get("sessions"),
            "point_R": est["point"], "ci_low_R": lo, "ci_high_R": hi,
            "theta_R": theta,
            "confirmatory": classify_primary(est["point"], lo, hi, theta),
            **screen_vs_zero(lo, hi, theta),
            "operable": est.get("n", 0) >= 800,
        }
    return pack


def _seed(text):
    return int(hashlib.sha256(str(text).encode()).hexdigest()[:16], 16)


def _intended_label(name, delta):
    if name == "boundary_inconclusive":
        return "INCONCLUSIVE"
    if delta > THETA_R or delta < -THETA_R:
        return "POSITIVE"
    if delta == 0.0:
        return "NULL"
    return "INCONCLUSIVE"


def simulate_label_feasibility(sd_R, n=800, sessions=400, reps=200, boot=399,
                               seed="C2-feasibility-v1"):
    """Fixed-seed classifier-operability simulation for one (n, sd) pair.

    ``sd_R`` is REQUIRED: contrast dispersion must be empirically anchored
    (PROTOCOL 2026-09-04), never defaulted. Draws are clipped to the
    registered contrast bounds. Gating covers only the three informative
    scenarios (prereg section 6a); boundary and near-threshold are reported.
    """
    if sd_R is None or not float(sd_R) > 0:
        raise ValueError("per-contrast sd_R must be a positive anchored number")
    if sessions >= n or n % sessions:
        raise ValueError(
            "feasibility simulation requires sessions < n and balanced clusters")
    sd = float(sd_R)
    rng = np.random.default_rng(_seed(f"{seed}:n{n}:sd{sd:g}"))
    fired = {name: 0 for name in SCENARIOS}
    expected = {name: _intended_label(name, delta)
                for name, delta in SCENARIOS.items()}
    obs_per_cluster = n // sessions
    for name, delta in SCENARIOS.items():
        for _ in range(reps):
            values = np.clip(
                rng.normal(delta, sd, size=(sessions, obs_per_cluster)),
                CONTRAST_WINSOR_R[0], CONTRAST_WINSOR_R[1])
            cluster_means = values.mean(axis=1)
            point = float(cluster_means.mean())
            idx = rng.integers(0, sessions, size=(boot, sessions))
            boots = cluster_means[idx].mean(axis=1)
            lo = float(np.quantile(boots, 0.025, method="lower"))
            hi = float(np.quantile(boots, 0.975, method="lower"))
            if classify_primary(point, lo, hi) == expected[name]:
                fired[name] += 1
    rates = {name: fired[name] / reps for name in SCENARIOS}
    return {"n": n, "sessions": sessions, "sd_R": sd, "reps_per_scenario": reps,
            "seed": seed, "theta_R": THETA_R, "fire_floor": FIRE_FLOOR,
            "contrast_winsor_R": list(CONTRAST_WINSOR_R),
            "scenarios": {name: {"delta_R": SCENARIOS[name],
                                 "expected_label": expected[name],
                                 "fire_rate": rates[name],
                                 "gating": name in OPERABILITY_SCENARIOS}
                          for name in SCENARIOS},
            "informative_pass": all(rates[name] >= FIRE_FLOOR
                                    for name in OPERABILITY_SCENARIOS),
            "primary_cell": PRIMARY_CELL,
            "primary_horizon_min": PRIMARY_HORIZON_MIN,
            "bounded_estimator": "paired contrast bounded to [-2.5R,+2.5R]; "
                                 "each arm winsorized to [-0.5R,+2.0R]"}


def feasibility_grid(sd_R, reps=200, seed="C2-feasibility-v1"):
    """Full grid at one anchored dispersion; minimum passing n over the grid."""
    points = [simulate_label_feasibility(sd_R, n, sessions=n // 2, reps=reps,
                                         seed=seed)
              for n in FEASIBILITY_GRID]
    passing = [p["n"] for p in points if p["informative_pass"]]
    return {"sd_R": float(sd_R), "grid": points,
            "minimum_passing_n": min(passing) if passing else None,
            "all_informative_firing": bool(passing),
            "boundary_emissible": any(
                p["scenarios"]["boundary_inconclusive"]["fire_rate"]
                >= FIRE_FLOOR for p in points),
            "mde_fire_rate_by_n": {
                p["n"]: p["scenarios"]["near_threshold_positive"]["fire_rate"]
                for p in points}}


def dispersion_sensitivity(reps=200, seed="C2-feasibility-v1"):
    """The four preregistered dispersion inputs, each fully reported.

    ``floor`` and ``central`` are recomputed live from the committed E19B-R
    FT ledgers (independence floor sqrt(2)*per-arm sd = 1.4481R; anti-
    correlated trimodal central 1.6015R from P(target-first)=0.2052; the
    directive's 1.45/1.581 match to rounding at p=0.2). 1.0R and 2.0R are
    the declared sensitivity bracket.
    """
    stats = ledger_contrast_dispersion()
    labeled = {"floor": 2 ** 0.5 * stats["per_arm_sd_R"],
               "central": stats["contrast_sd_trimodal_central_R"],
               "sensitivity_low": 1.0, "sensitivity_high": 2.0}
    runs = {name: feasibility_grid(sd, reps=reps, seed=seed)
            for name, sd in labeled.items()}
    passing = {name: r["minimum_passing_n"] for name, r in runs.items()
               if r["minimum_passing_n"] is not None}
    return {"anchor_provenance": stats,
            "labeled_densities": labeled, "runs": runs,
            "frozen_central_minimum_passing_n":
                runs["central"]["minimum_passing_n"],
            "sensitivity_minimum_passing_ns":
                {name: r["minimum_passing_n"] for name, r in runs.items()},
            "all_boundary_emissible": all(r["boundary_emissible"]
                                          for r in runs.values()),
            "reps_per_scenario": reps, "seed": seed, "theta_R": THETA_R,
            "fire_floor": FIRE_FLOOR,
            "frozen_post_data_gate": (
                "at achieved n/sessions/sd: the three informative scenarios "
                "fire >=80%; achieved n >= central minimum_passing_n; "
                "sensitivity range published alongside (prereg 6c)"
                if passing else
                "STAND DOWN: no grid point passes informative labels at any "
                "anchored dispersion")}
