import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request
PID = 35506697
BID = "4d6b52b49c36e5f24ce724f3b4603d06"
d = request("backtests/read", {"projectId": PID, "backtestId": BID})
bt = d.get("backtest", d)
print("status:", bt.get("status"))
print("error:", str(bt.get("error"))[:600])
rt = bt.get("runtimeStatistics") or {}
for k in sorted(rt.keys()):
    if k.startswith(("d_", "f_sessions", "f_no_")):
        print(k, "=", str(rt[k])[:400])
