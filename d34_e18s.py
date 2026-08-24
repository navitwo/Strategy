"""E18S: parallel variant rerun on v2.4 atomic engine.

All variants share ONE immutable candidate population (same exp_hash base
params, same signal/window/stop/target; only the studied factor differs).
Strict identity gates must pass on every run.
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
    ("E18S-candidate", {"variant": "candidate"}),
    ("E18S-shadowMOC", {"variant": "shadow_moc"}),
    ("E18S-ablCISD", {"variant": "ablate_cisd"}),
    ("E18S-ablFVG", {"variant": "ablate_fvg"}),
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
        with open(ROOT + r"\e18s_results.jsonl", "a") as f:
            f.write(json.dumps({"name": name, "bid": bid,
                                "error": str(res.get("error"))[:500]}) + "\n")
        print(f"FAILED: {name}: {str(res.get('error'))[:250]}", flush=True)
        continue
    rt = res.get("runtimeStatistics") or {}
    with open(ROOT + r"\e18s_results.jsonl", "a") as f:
        f.write(json.dumps({"name": name, "bid": bid,
                            "rt": {k: str(v) for k, v in rt.items()}}) + "\n")
    keep = ("r_trades", "r_wins", "r_avg", "r_pf", "r_avgwin", "r_avgloss",
            "rec_ok", "rec_i1_resid", "f_anomalous_exit_events",
            "d_cycles_opened", "d_atomic_exits", "f_untracked_fills",
            "f_late_fill_events", "bars_per_session")
    print(json.dumps({"name": name,
                      **{k: rt.get(k) for k in keep}}), flush=True)
