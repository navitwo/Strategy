import sys, os, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
os.chdir(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import backtest_create, poll_backtest
PID = 35506697
COMPILE = open("compile_id.txt").read().strip()
params = {"start_date": "2023-01-03", "end_date": "2023-03-31",
          "run_segment": "dev", "instrument": "ES",
          "risk_usd": "10000", "max_contracts": "1",
          "variant": "events_only"}
r = backtest_create(PID, "ESM-probe", params, compile_id=COMPILE)
print("bid:", r["backtest_id"], flush=True)
res = poll_backtest(PID, r["backtest_id"], max_wait=900, poll_s=10)
bt = res if isinstance(res, dict) else {}
print("status:", bt.get("status"))
err = str(bt.get("error", ""))[:300]
if err:
    print("err:", err)
rt = bt.get("runtimeStatistics") or {}
print({k: rt.get(k) for k in ("f_L_attempts", "f_S_attempts",
                              "d_ev_results", "os_events")})
