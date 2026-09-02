"""Campaign-2 bounded primary estimator and feasibility proof."""
import hashlib
import math
import random

THETA_R = 0.2
PRIMARY_CELL = "T2S0.5"
PRIMARY_HORIZON_MIN = 120
WINSOR_BOUNDS_R = (-0.5, 2.0)


def classify_primary(point, ci_low, ci_high, theta=THETA_R):
    if ci_low > theta:
        return "POSITIVE"
    if ci_high < theta:
        return "NULL"
    return "INCONCLUSIVE"


def _seed(text):
    return int(hashlib.sha256(str(text).encode()).hexdigest()[:16], 16)


def _cluster_ci(values, cluster_ids, reps, rng):
    clusters = sorted(set(cluster_ids))
    by_cluster = {c: [v for v, k in zip(values, cluster_ids) if k == c]
                  for c in clusters}
    means = []
    for _ in range(reps):
        selected = rng.choices(clusters, k=len(clusters))
        sample = [v for c in selected for v in by_cluster[c]]
        means.append(sum(sample) / len(sample))
    means.sort()
    lo = means[int(0.025 * (len(means) - 1))]
    hi = means[int(0.975 * (len(means) - 1))]
    return lo, hi


def simulate_label_feasibility(n=800, sessions=400, reps=200,
                               seed="C2-feasibility-v1"):
    """Pre-data simulation at a conservative achievable sample size.

    Two bounded observations per session preserve genuine session clustering.
    Three fixed data-generating means are used solely to prove the classifier
    can emit all three labels; they are not power claims about market data.
    """
    if sessions >= n or n % sessions:
        raise ValueError("feasibility simulation requires sessions < n and balanced clusters")
    rng = random.Random(_seed(seed))
    labels = {"POSITIVE": 0, "NULL": 0, "INCONCLUSIVE": 0}
    scenarios = {"POSITIVE": 0.55, "NULL": 0.00, "INCONCLUSIVE": THETA_R}
    cluster_ids = [i % sessions for i in range(n)]
    for expected, mean in scenarios.items():
        for iteration in range(reps):
            # bounded pseudo-payoffs mimic the pre-registered winsor range
            values = [min(WINSOR_BOUNDS_R[1], max(WINSOR_BOUNDS_R[0],
                      mean + rng.gauss(0, 0.45))) for _ in range(n)]
            point = sum(values) / n
            lo, hi = _cluster_ci(values, cluster_ids, 399, rng)
            label = classify_primary(point, lo, hi)
            if label == expected:
                labels[label] += 1
    return {"n": n, "sessions": sessions, "reps_per_scenario": reps,
            "labels_fired": labels, "theta_R": THETA_R,
            "primary_cell": PRIMARY_CELL,
            "primary_horizon_min": PRIMARY_HORIZON_MIN,
            "bounded_estimator": "mean payoff winsorized to [-0.5R,+2.0R]"}
