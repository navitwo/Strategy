import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request
PID = 35506697
BID = "3e1475f610dd578e50a91f245b35de1a"  # null-full
d = request("backtests/read", {"projectId": PID, "backtestId": BID})
bt = d.get("backtest", d)
rt = bt.get("runtimeStatistics") or {}
fun = {k[2:]: v for k, v in rt.items() if k.startswith(("f_L", "f_S"))}
core = {k: v for k, v in fun.items() if k.endswith(("attempts", "fills", "submits", "skips"))}
print("core:", core)
print("h4_published:", rt.get("d_h4_published"))
print("sessions:", rt.get("funnel_sessions"))
print("exp_hash:", rt.get("exp_hash"))
