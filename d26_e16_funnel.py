import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request
PID = 35506697

# Signal runs produce almost no trades even after throttle removal.
# Check funnel: is it sweep scarcity (bias gate) or inversion scarcity?
for tag, bid in (("sig", "a2b7b9e754973a3e3683b6319ea660be"),
                 ("sig-gap", "5114c3f63b66e13f3aa6d9854c4d0352")):
    d = request("backtests/read", {"projectId": PID, "backtestId": bid})
    bt = d.get("backtest", d)
    rt = bt.get("runtimeStatistics") or {}
    fun = {k[2:]: v for k, v in rt.items() if k.startswith(("f_L", "f_S"))}
    keep = [k for k in fun if any(t in k for t in
            ("attempts", "sweep_ok", "no_reclaim", "depth", "cisd_ok",
             "inv_ok", "inv_timeout", "fills", "submits"))]
    core = {k: fun[k] for k in sorted(keep)}
    print(f"--- {tag}")
    print(json.dumps(core, indent=1))
