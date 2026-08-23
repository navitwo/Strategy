import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import backtest_create, poll_backtest

PID = 35506697
COMPILE = "d7bf4c500f3b2239d34386851b1c3fa9-4fbf1c3682a30518e429228239cbcc74"
NAME = "DIAG-SCIFVG-probe-contracts-sessions"
params = {"start_date": "2024-06-03", "end_date": "2024-06-14", "run_segment": "full"}

bt = backtest_create(PID, NAME, params, compile_id=COMPILE)
bid = bt["backtest_id"]
print("submitted:", bid)
r = poll_backtest(PID, bid, max_wait=1500, poll_s=10)
print("status:", r.get("status"), "| error:", str(r.get("error"))[:400])
perf = r.get("totalPerformance") or {}
print("has perf:", bool(perf))
stats = r.get("statistics") or {}
print("stats:", json.dumps(stats)[:600])

# save raw for inspection
with open(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy\probe_result.json", "w") as f:
    json.dump({"id": bid, "status": r.get("status"), "stats": stats,
               "runtime": r.get("runtimeStatistics") or {}}, f, indent=2)
print("saved probe_result.json")
