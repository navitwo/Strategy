"""E19B offline analysis: session-block bootstrap on the EVENT ledger.

Pre-registered inference (PREREGISTRATION_E19B.md §4 amended, §7):
- Population: rows where bias_aligned == True, pooled across markets.
- Δ = mean side-aligned forward R-drift at the primary horizon H*.
- Session-block (trading-day) bootstrap, B resamples, day-level clusters,
  percentile two-sided 95% CI.
- Three-outcome rule anchored at θ = 0.2R:
    POSITIVE     if CI_lower > θ
    NULL         if CI_upper < θ
    INCONCLUSIVE otherwise (straddles θ)
- MDE reported as a pre-run power diagnostic only.

Usage:
    python e19b_bootstrap.py events.jsonl [--horizon 120] [--B 10000]
        [--theta 0.2] [--alpha 0.05]

Self-test:
    python e19b_bootstrap.py --selftest
"""
import json
import random
import sys
from collections import defaultdict


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                if r.get("bias_aligned") is True:
                    rows.append(r)
    return rows


def session_blocks(rows):
    """Group row indices by trading day (session block)."""
    by_day = defaultdict(list)
    for i, r in enumerate(rows):
        by_day[r["date"]].append(i)
    return [idxs for _, idxs in sorted(by_day.items())]


def boot_ci(vals, blocks, B, alpha, rng):
    """Percentile CI for the mean via day-cluster resampling."""
    n = len(vals)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    nb = len(blocks)
    sizes = [len(b) for b in blocks]
    tot_all = [sum(vals[i] for i in b) for b in blocks]
    means = []
    for _ in range(B):
        tot = 0.0
        cnt = 0
        for _b in range(nb):
            j = rng.randrange(nb)
            tot += tot_all[j]
            cnt += sizes[j]
        if cnt:
            means.append(tot / cnt)
    means.sort()
    lo = means[int((alpha / 2) * len(means))]
    hi = means[min(len(means) - 1, int((1 - alpha / 2) * len(means)))]
    obs = sum(vals) / n
    return obs, lo, hi


def mde(n_days, sigma_day, alpha=0.05, power=0.80):
    """Approximate two-sample-free MDE for a one-sample design at day level."""
    from statistics import NormalDist
    z_a = NormalDist().inv_cdf(1 - alpha / 2)
    z_b = NormalDist().inv_cdf(power)
    return (z_a + z_b) * sigma_day / max(math_sqrt(n_days), 1e-12)


def math_sqrt(x):
    x0 = x
    g = x / 2.0 or 1.0
    while abs(g * g - x0) > 1e-12:
        g = (g + x0 / g) / 2.0
    return g


def analyze(rows, horizon, B, theta, alpha, seed=20260825, verbose=True):
    # Δ population: primary-arm rows ONLY (bias_aligned==True). The counter
    # arm is a within-candidate contrast, never merged into Δ (§5).
    sel = [r for r in rows if int(r["h_min"]) == horizon
           and r.get("arm", "primary") == "primary"]
    # counter-arm within-candidate contrast (exploratory report)
    by_id = defaultdict(dict)
    for r in rows:
        by_id[r["event_id"]][r.get("arm", "primary")] = r["ret_r"]
    vals = [r["ret_r"] for r in sel]
    days = sorted({r["date"] for r in sel})
    blocks = session_blocks(sel)
    # day-level sd of daily means -> MDE diagnostic
    day_means = []
    for d in days:
        dv = [r["ret_r"] for r in sel if r["date"] == d]
        day_means.append(sum(dv) / len(dv))
    mu = sum(day_means) / len(day_means) if day_means else float("nan")
    var = (sum((m - mu) ** 2 for m in day_means) / (len(day_means) - 1)
           if len(day_means) > 1 else float("nan"))
    sd = var ** 0.5 if var == var else float("nan")
    mde_v = mde(len(blocks), sd, alpha) if sd == sd and blocks else float("nan")

    obs, lo, hi = boot_ci(vals, blocks, B, alpha,
                          random.Random(seed))
    if verbose:
        print(f"n={len(vals)} days={len(blocks)} "
              f"mean={obs:.4f}R CI=[{lo:.4f}, {hi:.4f}] theta={theta} "
              f"MDE(diagnostic)={mde_v:.4f}R")
        if lo > theta:
            verdict = "POSITIVE"
        elif hi < theta:
            verdict = "NULL"
        else:
            verdict = "INCONCLUSIVE"
        print(f"VERDICT ({horizon}min): {verdict}")
    # counter contrast: mean(primary - counter_ret) per candidate
    pairs = [(v.get("primary"), v.get("counter")) for v in by_id.values()]
    pairs = [(p, c) for p, c in pairs if p is not None and c is not None]
    contrast = (sum(p - c for p, c in pairs) / len(pairs)) if pairs else None
    return {"n": len(vals), "days": len(blocks), "obs": obs, "lo": lo,
            "hi": hi, "theta": theta, "mde": mde_v, "contrast": contrast}


# ---------------- self-tests with synthetic fixtures ----------------
def _fixture(kind, seed=7):
    """Synthetic event ledgers: positive / null / inconclusive vs theta=0.2.

    Day-clustered: 40 days x 10 candidates; counter arm mirrors primary
    around a small offset so pairing exists but never drives Δ.
    """
    rng = random.Random(seed)
    rows = []
    eid = 0
    for d in range(40):
        date = f"2024-{(d // 20) + 1:02d}-{(d % 20) + 1:02d}"
        shift = {"positive": 0.35, "null": -0.10,
                 "inconclusive": 0.22}[kind]
        for _ in range(10):
            eid += 1
            base = shift + rng.gauss(0, 0.25)
            rows.append({"event_id": f"E{eid:05d}", "bias_aligned": True,
                         "arm": "primary", "date": date, "h_min": 120,
                         "ret_r": round(base, 6)})
            rows.append({"event_id": f"E{eid:05d}", "bias_aligned": True,
                         "arm": "counter", "date": date, "h_min": 120,
                         "ret_r": round(-base + 0.05, 6)})
    return rows


def selftest():
    ok = True
    for kind, expect in (("positive", "POSITIVE"),
                         ("null", "NULL"),
                         ("inconclusive", "INCONCLUSIVE")):
        rows = _fixture(kind)
        # capture verdict without printing per-line noise
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            res = analyze(rows, 120, B=2000, theta=0.2, alpha=0.05,
                          seed=42, verbose=False)
        if lo_expects(res, expect):
            print(f"PASS fixture {kind}: {res['lo']:.3f}/{res['hi']:.3f} "
                  f"-> {expect}")
        else:
            print(f"FAIL fixture {kind}: CI [{res['lo']:.3f},{res['hi']:.3f}]"
                  f" expected {expect}")
            ok = False
    print("SELFTEST:", "PASS" if ok else "FAIL")
    return ok


def lo_expects(res, expect):
    if expect == "POSITIVE":
        return res["lo"] > res["theta"]
    if expect == "NULL":
        return res["hi"] < res["theta"]
    return res["lo"] <= res["theta"] <= res["hi"]


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--selftest" in args:
        sys.exit(0 if selftest() else 1)
    path = next((a for a in args if not a.startswith("--")), "events.jsonl")
    hz = int(args[args.index("--horizon") + 1]) if "--horizon" in args else 120
    Bv = int(args[args.index("--B") + 1]) if "--B" in args else 10000
    th = float(args[args.index("--theta") + 1]) if "--theta" in args else 0.2
    al = float(args[args.index("--alpha") + 1]) if "--alpha" in args else 0.05
    rows = load_rows(path)
    analyze(rows, hz, Bv, th, al)
