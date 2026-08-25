import sys, os
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
os.chdir(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import backtest_create, poll_backtest
PID = 35506697
COMPILE = open("compile_id.txt").read().strip()
for inst in ("YM", "RTY"):
    params = {"start_date": "2023-01-03", "end_date": "2023-02-28",
              "run_segment": "dev", "instrument": inst,
              "risk_usd": "10000", "max_contracts": "1",
              "variant": "events_only"}
    r = backtest_create(PID, f"{inst}-probe", params, compile_id=COMPILE)
    print(inst, "bid:", r["backtest_id"], flush=True)
    res = poll_backtest(PID, r["backtest_id"], max_wait=900, poll_s=10)
    bt = res if isinstance(res, dict) else {}
    err = str(bt.get("error", ""))[:220]
    rt = bt.get("runtimeStatistics") or {}
    atts = int(rt.get("f_L_attempts", 0) or 0) + int(rt.get("f_S_attempts", 0) or 0)
    print(inst, bt.get("status"), "| att:", atts,
          "| ev:", rt.get("d_ev_results"), "| os:", rt.get("os_events"),
          ("| ERR: " + err) if err else "", flush=True)
