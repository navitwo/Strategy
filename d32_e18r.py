"""E18R: dev-period rerun on engine v2.3 (all correctness gates passed).

Candidate + paired shadow/ablation variants. Exports complete
candidate/trade/order ledgers from Debug output for offline bootstrap CIs.
"""
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
    ("E18R-candidate", {"variant": "candidate"}),
    ("E18R-shadowMOC", {"variant": "shadow_moc"}),
    ("E18R-ablCISD", {"variant": "ablate_cisd"}),
    ("E18R-ablFVG", {"variant": "ablate_fvg"}),
]

for name, extra in RUNS:
    params = {**BASE, **extra}
    try:
        r = backtest_create(PID, name, params, compile_id=COMPILE)
    except Exception as e:
        print(name, "SUBMIT FAIL:", str(e)[:200], flush=True)
        continue
    bid = r["backtest_id"]
    print("submitted", name, bid, flush=True)
    res = poll_backtest(PID, bid, max_wait=3600, poll_s=15)
    if res.get("status") in ("RuntimeError", "poll-timeout"):
        err = res.get("error")
        print(f"FAILED: {name}: {str(err)[:300]}", flush=True)
        with open(ROOT + r"\e18r_results.jsonl", "a") as f:
            f.write(json.dumps({"name": name, "bid": bid,
                                "status": res.get("status"),
                                "error": str(err)[:500]}) + "\n")
        continue
    rt = res.get("runtimeStatistics") or {}
    out = {"name": name, "bid": bid, "rt": {k: str(v) for k, v in rt.items()}}
    with open(ROOT + r"\e18r_results.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")
    keep = ("r_trades", "r_wins", "r_avg", "r_pf", "r_avgwin", "r_avgloss",
            "rec_ok", "rec_i1_resid", "rec_i2_resid", "f_oco_void_legs",
            "f_oco_races", "f_untracked_fills", "f_late_fill_events")
    print(json.dumps({"name": name, **{k: rt.get(k) for k in keep}}), flush=True)
