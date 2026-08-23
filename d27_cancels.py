"""E16d: diagnose why only 7/122 CISD chains submit entries.

Suspect: retest limit at zone proximal edge almost never fills because price
tags it intrabar but the 5m close has already moved away, OR pending cancels
dominate. Pull cancel counters and submits vs fills from the funnel.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request
PID = 35506697

d = request("backtests/read", {"projectId": PID,
                               "backtestId": "a2b7b9e754973a3e3683b6319ea660be"})
bt = d.get("backtest", d)
rt = bt.get("runtimeStatistics") or {}
fun = {k[2:]: v for k, v in rt.items() if k.startswith(("f_L", "f_S"))}
cancels = {k: v for k, v in fun.items() if "cancel" in k}
print(json.dumps(cancels, indent=1))
print("L_inv_ok:", fun.get("L_inv_ok"), "| L_submits:", fun.get("L_submits"))
