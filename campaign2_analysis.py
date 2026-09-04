"""Campaign-2 bounded primary estimator and feasibility grid."""
import hashlib

import numpy as np

THETA_R = 0.2
PRIMARY_CELL = "T2S0.5"
PRIMARY_HORIZON_MIN = 120
WINSOR_BOUNDS_R = (-0.5, 2.0)
FEASIBILITY_GRID = (200, 400, 800, 1600, 3200)
SIM_PER_OBS_SD_R = 0.45
FIRE_FLOOR = 0.80

# The four operability scenarios decide the pre-registered pass/fail gate;
# the near-threshold scenario is an MDE probe reported regardless of the
# answer (prereg section 6, amendment 2026-09-04).
OPERABILITY_SCENARIOS = {
    "reversal_positive": +0.55,
    "continuation_positive": -0.55,
    "null_equivalent": 0.0,
    "boundary_inconclusive": +THETA_R,
}
MDE_SCENARIOS = {"near_threshold_positive": 0.3}
SCENARIOS = {**OPERABILITY_SCENARIOS, **MDE_SCENARIOS}


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


def _seed(text):
    return int(hashlib.sha256(str(text).encode()).hexdigest()[:16], 16)


def _intended_label(name, delta):
    if name == "boundary_inconclusive":
        # true mean sits exactly on theta: no honest CI geometry earns
        # POSITIVE or NULL, so INCONCLUSIVE is the informative target
        return "INCONCLUSIVE"
    if delta > THETA_R or delta < -THETA_R:
        return "POSITIVE"
    if delta == 0.0:
        return "NULL"
    return "INCONCLUSIVE"


def simulate_label_feasibility(n=800, sessions=400, reps=200, boot=399,
                               seed="C2-feasibility-v1"):
    """Fixed-seed classifier-operability simulation for one grid point.

    Two bounded observations per session-date cluster preserve genuine
    clustering. Scenarios are fixed data-generating means, not power claims.
    ``all_scenarios_pass`` covers only the four operability scenarios; the
    near-threshold MDE probe is reported per grid point but never gates.
    """
    if sessions >= n or n % sessions:
        raise ValueError(
            "feasibility simulation requires sessions < n and balanced clusters")
    rng = np.random.default_rng(_seed(f"{seed}:n{n}"))
    fired = {name: 0 for name in SCENARIOS}
    expected = {name: _intended_label(name, delta)
                for name, delta in SCENARIOS.items()}
    obs_per_cluster = n // sessions
    for name, delta in SCENARIOS.items():
        for _ in range(reps):
            values = np.clip(
                rng.normal(delta, SIM_PER_OBS_SD_R,
                           size=(sessions, obs_per_cluster)),
                WINSOR_BOUNDS_R[0], WINSOR_BOUNDS_R[1])
            cluster_means = values.mean(axis=1)
            point = float(cluster_means.mean())
            idx = rng.integers(0, sessions, size=(boot, sessions))
            boots = cluster_means[idx].mean(axis=1)
            lo = float(np.quantile(boots, 0.025, method="lower"))
            hi = float(np.quantile(boots, 0.975, method="lower"))
            if classify_primary(point, lo, hi) == expected[name]:
                fired[name] += 1
    rates = {name: fired[name] / reps for name in SCENARIOS}
    return {"n": n, "sessions": sessions, "reps_per_scenario": reps,
            "seed": seed, "per_obs_sd_R": SIM_PER_OBS_SD_R,
            "theta_R": THETA_R, "fire_floor": FIRE_FLOOR,
            "scenarios": {name: {"delta_R": SCENARIOS[name],
                                 "expected_label": expected[name],
                                 "fire_rate": rates[name],
                                 "passes": rates[name] >= FIRE_FLOOR}
                          for name in SCENARIOS},
            "all_scenarios_pass": all(
                rates[name] >= FIRE_FLOOR for name in OPERABILITY_SCENARIOS),
            "primary_cell": PRIMARY_CELL,
            "primary_horizon_min": PRIMARY_HORIZON_MIN,
            "bounded_estimator": "mean payoff winsorized to [-0.5R,+2.0R]"}


def feasibility_grid(reps=200, seed="C2-feasibility-v1"):
    """Run every preregistered grid point; report the minimum passing n.

    The minimum passing n (four operability scenarios each >=80%) is the
    frozen post-data pass/fail number. No passing grid point means
    pre-registered stand-down. The near-threshold firing profile is frozen
    as the declared MDE statement regardless of its answer.
    """
    points = [simulate_label_feasibility(n, sessions=n // 2, reps=reps,
                                         seed=seed)
              for n in FEASIBILITY_GRID]
    passing = [p["n"] for p in points if p["all_scenarios_pass"]]
    mde_profile = {p["n"]: p["scenarios"]["near_threshold_positive"]["fire_rate"]
                   for p in points}
    mde_passing = [p["n"] for p in points
                   if p["scenarios"]["near_threshold_positive"]["passes"]]
    return {"grid": points,
            "minimum_passing_n": min(passing) if passing else None,
            "all_firing": bool(passing),
            "frozen_post_data_gate": ("achieved n >= minimum_passing_n; at "
                                      "achieved n/sd POSITIVE and NULL fire "
                                      ">=80% (INCONCLUSIVE emissibility "
                                      "already shown on the grid; see prereg "
                                      "section 6a)" if passing else
                                      "STAND DOWN: no grid point passes"),
            "mde_probe": {
                "delta_R": MDE_SCENARIOS["near_threshold_positive"],
                "fire_rate_by_n": mde_profile,
                "minimum_passing_n": min(mde_passing) if mde_passing else None,
                "statement": (
                    "0.3R detectable at n>="
                    f"{min(mde_passing)}" if mde_passing else
                    "0.3R NOT reliably detectable at any grid n: the "
                    "0.2-0.55R band is declared undetectable at achievable "
                    "size; this is the minimum detectable effect record")},
            "scenarios": dict(SCENARIOS),
            "operability_scenarios": list(OPERABILITY_SCENARIOS),
            "reps_per_scenario": reps, "seed": seed,
            "theta_R": THETA_R, "per_obs_sd_R": SIM_PER_OBS_SD_R}
