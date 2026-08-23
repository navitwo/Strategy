"""E16b: null-probability calibration probe (NQ, 2010-2024).

p=0.006 produced only ~30 fills because most candidate bars fail the
min-stop-distance filter (4 ticks). Raise p until fills land in the 150-250
band. Single short probe run, then the calibrated p feeds the final study.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
from qc_api import backtest_create, poll_backtest

PID = 35506697
COMPILE = open(ROOT + r"\compile_id.txt").read().strip()

for p in ("0.02", "0.04"):
    params = {"start_date": "2010-01-01", "end_date": "2024-12-31",
              "run_segment": "full", "instrument": "NQ", "risk_usd": "10000",
              "entry_mode": "random", "random_entry_prob": p}
    r = backtest_create(PID, f"E16b-nullprobe-p{p.replace('.','')}", params,
                        compile_id=COMPILE)
    bid = r["backtest_id"]
    print("submitted", p, bid)
    res = poll_backtest(PID, bid, max_wait=3600, poll_s=15)
    if res.get("status") in ("RuntimeError", "poll-timeout"):
        print("FAILED:", str(res.get("error"))[:200]); continue
    rt = res.get("runtimeStatistics") or {}
    out = {"p": p, "trades": rt.get("r_trades"), "wins": rt.get("r_wins"),
           "avg_r": rt.get("r_avg"), "sum_r": rt.get("r_sum"),
           "rec_ok": rt.get("rec_ok")}
    with open(ROOT + r"\e16_results.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")
    print(json.dumps(out))
