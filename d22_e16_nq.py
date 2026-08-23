"""E16: corrected full-history gate study (signal + null, NQ, 1 contract).

Changes vs d21: instrument=NQ (history to ~2010), risk_usd set high enough
that exactly 1 contract always trades (risk accounting per-contract, so R is
sizing-independent and reconcile uses qty=1). R now uses ACTUAL fill prices.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
from qc_api import backtest_create, poll_backtest

PID = 35506697

# risk_usd = 10000 with point_value 20 -> any stop distance up to 500 pts
# sizes to 1 contract; R math is per-contract so results are sizing-free.
BASE = {"start_date": "2010-01-01", "end_date": "2024-12-31",
        "run_segment": "full", "instrument": "NQ", "risk_usd": "10000"}

CONFIGS = [
    ("sig-full", {}),
    ("null-full", {"entry_mode": "random", "random_entry_prob": "0.006"}),
    ("sig-gapstop", {"stop_mode": "gap"}),
    ("null-gapstop", {"stop_mode": "gap", "entry_mode": "random",
                      "random_entry_prob": "0.008"}),
]

for name, extra in CONFIGS:
    params = {**BASE, **extra}
    r = backtest_create(PID, f"E16-{name}", params,
                        compile_id=open(ROOT + r"\compile_id.txt").read().strip())
    bid = r["backtest_id"]
    print("submitted", name, bid)
    res = poll_backtest(PID, bid, max_wait=3600, poll_s=15)
    if res.get("status") in ("RuntimeError", "poll-timeout"):
        print("FAILED:", name, str(res.get("error"))[:200])
        continue
    rt = res.get("runtimeStatistics") or {}
    rec = {k: rt.get(k) for k in ("rec_ok", "rec_exp_usd", "rec_obs_usd",
                                  "rec_resid", "fills_vs_trades")}
    out = {"name": name, "bid": bid,
           "trades": rt.get("r_trades"), "wins": rt.get("r_wins"),
           "avg_r": rt.get("r_avg"), "pf": rt.get("r_pf"),
           "sum_r": rt.get("r_sum"), "reconcile": rec}
    with open(ROOT + r"\e16_results.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")
    print(json.dumps(out)[:500])
