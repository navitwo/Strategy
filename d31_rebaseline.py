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
    ("E17a-sig", {}),
    ("E17b-null-p002", {"entry_mode": "random", "random_entry_prob": "0.02"}),
    ("E17c-null-p006", {"entry_mode": "random", "random_entry_prob": "0.06"}),
    ("E17d-sig-gap", {"stop_mode": "gap"}),
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
    fun = {k[2:]: int(v) for k, v in rt.items() if k.startswith(("f_L", "f_S"))}
    out = {
        "name": name, "bid": bid,
        "trades": int(rt.get("r_trades", 0)),
        "wins": int(rt.get("r_wins", 0)),
        "avg_r": float(rt.get("r_avg", 0)),
        "pf_r": float(rt.get("r_pf", 0)),
        "sum_r": float(rt.get("r_sum", 0)),
        "rec_ok": rt.get("rec_ok"),
        "rec_resid": rt.get("rec_resid"),
        "flatten_fills": fun.get("flatten_fills", 0),
        "untracked_fills": fun.get("untracked_fills", 0),
        "oco_races": fun.get("oco_races", 0),
        "eod_flattens": fun.get("eod_flattens", 0),
        "h4_published": rt.get("d_h4_published"),
        "sessions": rt.get("funnel_sessions"),
        "L_fills": fun.get("L_fills", 0), "S_fills": fun.get("S_fills", 0),
    }
    with open(ROOT + r"\e17_results.jsonl", "a") as f:
        f.write(json.dumps(out) + "\n")
    print(json.dumps(out), flush=True)
