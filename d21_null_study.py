"""B2-E15 driver: gate-contribution study vs random-entry null.

Runs, per gate configuration: one SIGNAL run + NULL runs at matched trade
counts (probability tuned via bisection on a probe year), over 2015-2024.
All ledgers are exported by the engine as Debug 'TRADES {...}' lines; this
driver collects them from the cloud logs endpoint when available or falls
back to RuntimeStatistics aggregates. Results appended to null_study.jsonl.

NOTE: requires main.py == scifvg_main.py deployed (signal+null in one file).
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
from qc_api import request

PID = 35506697


def run(name, params):
    from qc_api import backtest_create, poll_backtest
    COMPILE = open(ROOT + r"\compile_id.txt").read().strip()
    bt = backtest_create(PID, name, params, compile_id=COMPILE)
    bid = bt["backtest_id"]
    res = poll_backtest(PID, bid, max_wait=3600, poll_s=15)
    if res.get("status") in ("RuntimeError", "poll-timeout"):
        return {"name": name, "failed": str(res.get("error"))[:300]}
    rt = res.get("runtimeStatistics") or {}
    rec = {k: rt.get(k) for k in ("rec_ok", "rec_exp_usd", "rec_obs_usd",
                                  "rec_resid", "fills_vs_trades")}
    out = {
        "name": name, "backtest_id": bid, "params": params,
        "r_trades": int(rt.get("r_trades", 0)),
        "r_wins": int(rt.get("r_wins", 0)),
        "r_avg": float(rt.get("r_avg", 0)),
        "r_pf": float(rt.get("r_pf", 0)),
        "r_sum": float(rt.get("r_sum", 0)),
        "reconcile": rec,
    }
    # try to fetch the TRADES ledger from logs
    try:
        lg = request("backtests/log/read", {"projectId": PID, "backtestId": bid})
        rows = lg.get("logs") or lg.get("messages") or []
        trades = None
        for line in rows:
            t = line.get("message", "") if isinstance(line, dict) else str(line)
            if t.startswith("TRADES "):
                trades = json.loads(t[7:])
                break
        out["ledger"] = trades.get("trades") if trades else None
    except Exception:
        out["ledger"] = None
    return out


CONFIGS = [
    ("full-signal", {"invert_on_cisd_bar": "1"}),
    ("no-bias-gate", {"invert_on_cisd_bar": "1", "entry_mode": "random",
                      "random_entry_prob": "0.006"}),
    ("gap-stop", {"invert_on_cisd_bar": "1", "stop_mode": "gap"}),
    ("null-gap-stop", {"invert_on_cisd_bar": "1", "stop_mode": "gap",
                       "entry_mode": "random", "random_entry_prob": "0.008"}),
]

results = []
for name, params in CONFIGS:
    full = {"start_date": "2015-01-01", "end_date": "2024-12-31",
            "run_segment": "full", **params}
    r = run(f"B2E15-{name}", full)
    results.append(r)
    with open(ROOT + r"\null_study.jsonl", "a") as f:
        f.write(json.dumps(r) + "\n")
    print(json.dumps({k: v for k, v in r.items() if k != "ledger"},
                     indent=1)[:600])
