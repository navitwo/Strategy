import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request

PID = 35506697
BID = open(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy\probe_backtest_id.txt").read().strip()
d = request("backtests/read", {"projectId": PID, "backtestId": BID})
bt = d.get("backtest", d)
print("backtest keys:", sorted(bt.keys()))
# any log-ish fields?
for k in bt.keys():
    if "log" in k.lower() or "debug" in k.lower() or "message" in k.lower():
        print("LOGFIELD", k, str(bt[k])[:500])
