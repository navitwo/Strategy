"""E18R-b: rerun shadowMOC + ablFVG after same-bar-cancel fix."""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
import os; os.chdir(ROOT)
from qc_api import backtest_create, poll_backtest

PID = 35506697
COMPILE = open(ROOT + r"\compile_id.txt").read().strip()
BASE = {"start_date": "2010-01-01", "end_date": "2024-12-31",
        "run_segment": "full", "instrument": "NQ",
        "risk_usd": "10000", "max_contracts": "1"}
RUNS = [
    ("E18R5-ablCISD", {"variant": "ablate_cisd"}),
]
for name, extra in RUNS:
    params = {**BASE, **extra}
    r = backtest_create(PID, name, params, compile_id=COMPILE)
    print("submitted", name, r["backtest_id"], flush=True)
    res = poll_backtest(PID, r["backtest_id"], max_wait=3600, poll_s=15)
    if res.get("status") in ("RuntimeError", "poll-timeout"):
        print(f"FAILED: {name}: {str(res.get('error'))[:300]}", flush=True)
        continue
    rt = res.get("runtimeStatistics") or {}
    with open(ROOT + r"\e18r_results.jsonl", "a") as f:
        f.write(json.dumps({"name": name, "bid": r["backtest_id"],
                            "rt": {k: str(v) for k, v in rt.items()}}) + "\n")
    keep = ("r_trades","r_wins","r_avg","r_pf","rec_ok","f_L_fills","f_S_fills")
    print(json.dumps({"name": name, **{k: rt.get(k) for k in keep}}), flush=True)
