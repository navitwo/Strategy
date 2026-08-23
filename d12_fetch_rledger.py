import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request

PID = 35506697
for name, bid in (("E01d", "b25973b542436f0f16503a227dc530cd"),
                  ("E02", "b5866e15a20d922aea7702fafce90694")):
    d = request("backtests/read", {"projectId": PID, "backtestId": bid})
    bt = d.get("backtest", d)
    rt = bt.get("runtimeStatistics") or {}
    rkeys = {k: v for k, v in rt.items() if not k.startswith(("f_", "d_", "funnel"))}
    print(name, json.dumps(rkeys, sort_keys=True))
