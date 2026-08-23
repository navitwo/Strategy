"""E16h: FINAL calibrated study — null p tuned to signal trade count.

Signal produces ~3 fills/15y (retest-at-proximal is the binding constraint).
Null calibrated to the same order of magnitude: p=0.0002 (expect ~3-6 fills
over 15y given 2010-2024 candidate bars). Runs 2 pairs (default & gap stop),
then computes gate contribution = signal_avgR - null_avgR per pair.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
from qc_api import backtest_create, poll_backtest

PID = 35506697
COMPILE = open(ROOT + r"\compile_id.txt").read().strip()

RUNS = [
    ("E16h-null", {"entry_mode": "random", "random_entry_prob": "0.0002"}),
    ("E16h-null-gap", {"stop_mode": "gap", "entry_mode": "random",
                       "random_entry_prob": "0.0002"}),
]

for name, extra in RUNS:
    params = {"start_date": "2010-01-01", "end_date": "2024-12-31",
              "run_segment": "full", "instrument": "NQ", "risk_usd": "10000",
              **extra}
    r = backtest_create(PID, name, params, compile_id=COMPILE)
    print("submitted", name, r["backtest_id"])
    res = poll_backtest(PID, r["backtest_id"], max_wait=3600, poll_s=15)
    rt = res.get("runtimeStatistics") or {}
    out = {"name": name, "bid": r["backtest_id"], "trades": rt.get("r_trades"),
           "wins": rt.get("r_wins"), "avg_r": rt.get("r_avg"),
           "sum_r": rt.get("r_sum"), "rec_ok": rt.get("rec_ok")}
    with open(ROOT + r"\e16_results.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")
    print(json.dumps(out))
