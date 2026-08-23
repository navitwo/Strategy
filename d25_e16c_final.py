"""E16c FINAL: gate-contribution study, NQ 1-contract, 2010-2024.

Calibrated null p=0.10 (expected ~150 fills). Four runs:
  1. signal (all gates)
  2. null   (random entry, same bracket geometry)
  3. signal + gap-stop variant
  4. null   + gap-stop variant
Gate contribution = (signal avg R) - (null avg R), per stop mode.
Bootstrap CIs computed offline from the per-trade ledgers.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
from qc_api import backtest_create, poll_backtest

PID = 35506697
COMPILE = open(ROOT + r"\compile_id.txt").read().strip()

CONFIGS = [
    ("E16c-sig", {}),
    ("E16c-null", {"entry_mode": "random", "random_entry_prob": "0.10"}),
    ("E16c-sig-gap", {"stop_mode": "gap"}),
    ("E16c-null-gap", {"stop_mode": "gap", "entry_mode": "random",
                       "random_entry_prob": "0.10"}),
]

for name, extra in CONFIGS:
    params = {"start_date": "2010-01-01", "end_date": "2024-12-31",
              "run_segment": "full", "instrument": "NQ", "risk_usd": "10000",
              **extra}
    r = backtest_create(PID, name, params, compile_id=COMPILE)
    bid = r["backtest_id"]
    print("submitted", name, bid)
    res = poll_backtest(PID, bid, max_wait=3600, poll_s=15)
    if res.get("status") in ("RuntimeError", "poll-timeout"):
        print("FAILED:", str(res.get("error"))[:200]); continue
    rt = res.get("runtimeStatistics") or {}
    out = {"name": name, "bid": bid, "trades": rt.get("r_trades"),
           "wins": rt.get("r_wins"), "avg_r": rt.get("r_avg"),
           "pf": rt.get("r_pf"), "sum_r": rt.get("r_sum"),
           "rec_ok": rt.get("rec_ok"), "rec_exp": rt.get("rec_exp_usd"),
           "rec_obs": rt.get("rec_obs_usd"), "rec_resid": rt.get("rec_resid")}
    with open(ROOT + r"\e16c_results.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")
    print(json.dumps(out))
