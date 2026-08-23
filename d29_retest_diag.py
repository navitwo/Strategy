"""E16g: retest-stage diagnosis — where do the 13 inversions die?

inv_ok=13, submits=13(?), fills=3. Check cancel reasons and whether the
proximal-edge limit is simply never touched (cancel_expiry should dominate).
If expiry dominates: the retest rarely comes back to the zone within 24 bars
=> entry model (limit-at-proximal) is the bottleneck, not the signal.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request
PID = 35506697

d = request("backtests/read", {"projectId": PID,
                               "backtestId": "23593a9b4b377b62c6d653a39d9ed871"})
bt = d.get("backtest", d)
rt = bt.get("runtimeStatistics") or {}
fun = {k[2:]: v for k, v in rt.items() if k.startswith(("f_L", "f_S"))}
print("L: inv_ok", fun.get("L_inv_ok"), "submits", fun.get("L_submits"),
      "fills", fun.get("L_fills"), "cancel_expiry", fun.get("L_cancel_expiry"),
      "cancel_invalid", fun.get("L_cancel_invalid"),
      "cancel_window", fun.get("L_cancel_window"))
print("S: inv_ok", fun.get("S_inv_ok"), "submits", fun.get("S_submits"),
      "fills", fun.get("S_fills"), "cancel_expiry", fun.get("S_cancel_expiry"),
      "cancel_invalid", fun.get("S_cancel_invalid"),
      "cancel_window", fun.get("S_cancel_window"))
