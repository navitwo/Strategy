import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request
PID = 35506697
BID = "1d132be5cab377eb110f3eb3e37d9fd8"   # latest NULL smoke run
d = request("backtests/read", {"projectId": PID, "backtestId": BID})
bt = d.get("backtest", d)
rt = bt.get("runtimeStatistics") or {}
fun = {k[2:]: v for k, v in rt.items() if k.startswith(("f_L", "f_S"))}
core = {k: v for k, v in fun.items() if k.endswith(("attempts", "fills", "submits"))}
print("status:", bt.get("status"))
print("exp_hash:", rt.get("exp_hash"))
print("core:", core)
print("Total Orders:", (bt.get("statistics") or {}).get("Total Orders"))
