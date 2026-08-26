import sys, os, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
os.chdir(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import backtest_create, poll_backtest
PID = 35506697
COMPILE = open("compile_id.txt").read().strip()
out = open("e19br_full_results.jsonl", "a")
for inst in ("NQ", "ES", "YM", "RTY"):
    min_ticks = {"NQ": 8, "ES": 8, "YM": 6, "RTY": 12}[inst]
    params = {"start_date": "2010-01-01", "end_date": "2024-12-31",
              "run_segment": "dev", "instrument": inst,
              "risk_usd": "10000", "max_contracts": "1",
              "variant": "events_only",
              "min_stop_ticks": str(min_ticks),
              "floor_atr_frac": "0.10"}
    tag = f"E19BR-{inst}"
    try:
        r = backtest_create(PID, tag, params, compile_id=COMPILE)
        print(inst, "submitted", r["backtest_id"], flush=True)
        res = poll_backtest(PID, r["backtest_id"], max_wait=7200, poll_s=20)
        bt = res if isinstance(res, dict) else {}
        rt = bt.get("runtimeStatistics") or {}
        rec = {"inst": inst, "bid": r["backtest_id"],
               "status": str(bt.get("status")),
               "error": str(bt.get("error", ""))[:300],
               "rt": {k: str(v) for k, v in rt.items()}}
        out.write(json.dumps(rec) + "\n")
        out.flush()
        atts = int(rt.get("f_L_attempts", 0) or 0) + int(rt.get("f_S_attempts", 0) or 0)
        print(inst, bt.get("status"), "| att:", atts,
              "| ev:", rt.get("d_ev_results"), "| os:", rt.get("os_events"),
              flush=True)
    except Exception as e:
        print(inst, "FAILED:", e, flush=True)
print("ALL MARKETS DONE", flush=True)
