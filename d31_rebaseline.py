"""E17 RE-BASELINE (post-v2.0 correctness fixes).

Everything prior is void. This is the first interpretable measurement.
NQ, 1 contract (max_contracts=1 AND risk_usd sized so qty==1), 2010-2024 dev.
Signal + calibrated nulls + gap-stop variant. Facts only; conclusions gated
on rec_ok == 1.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
from qc_api import backtest_create, poll_backtest

PID = 35506697
COMPILE = open(ROOT + r"\compile_id.txt").read().strip()

BASE = {"start_date": "2010-01-01", "end_date": "2024-12-31",
        "run_segment": "full", "instrument": "NQ",
        "risk_usd": "10000", "max_contracts": "1"}

RUNS = [
    ("E18a-sig", {}),
    ("E18b-null-p002", {"entry_mode": "random", "random_entry_prob": "0.02"}),
    ("E18c-null-p006", {"entry_mode": "random", "random_entry_prob": "0.06"}),
    ("E18d-sig-gap", {"stop_mode": "gap"}),
    ("E18e-null-gap", {"stop_mode": "gap", "entry_mode": "random",
                       "random_entry_prob": "0.06"}),
]

for name, extra in RUNS:
    params = {**BASE, **extra}
    try:
        r = backtest_create(PID, name, params, compile_id=COMPILE)
    except Exception as e:
        print(name, "SUBMIT FAIL:", str(e)[:200])
        continue
    bid = r["backtest_id"]
    print("submitted", name, bid, flush=True)
    res = poll_backtest(PID, bid, max_wait=3600, poll_s=15)
    if res.get("status") in ("RuntimeError", "poll-timeout"):
        print("FAILED:", name, str(res.get("error"))[:200], flush=True)
        continue
    rt = res.get("runtimeStatistics") or {}
    # review round 4: capture the WHOLE statistics dict - prefix filters hid
    # flatten_fills/untracked_fills/oco_races/eod_flattens and r_avgwin/r_avgloss.
    out = {"name": name, "bid": bid, "rt": {k: str(v) for k, v in rt.items()}}
    # convenience top-level for quick scanning
    for key in ("r_trades", "r_wins", "r_avg", "r_pf", "r_sum",
                "r_avgwin", "r_avgloss", "rec_ok"):
        out[key] = rt.get(key)
    out["rec_detail"] = {k: rt.get(k) for k in
                         ("rec_n_tradebuilder", "rec_i1_exp_usd",
                          "rec_i1_profit", "rec_i1_resid", "rec_fees_actual",
                          "rec_fees_modeled", "rec_i2_resid", "rec_tpv_delta",
                          "rec_i3_resid", "rec_fills_vs_trades")
                         if k in rt}
    with open(ROOT + r"\e17_results.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")
    print(json.dumps(out), flush=True)
