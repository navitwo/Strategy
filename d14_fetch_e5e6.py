import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request

PID = 35506697


def summarize(tag, out):
    txt = open(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy" + "\\" + out).read()
    bid = None
    for line in txt.splitlines():
        if line.startswith("submitted:"):
            bid = line.split(":", 1)[1].strip()
    d = request("backtests/read", {"projectId": PID, "backtestId": bid})
    bt = d.get("backtest", d)
    rt = bt.get("runtimeStatistics") or {}
    stats = bt.get("statistics") or {}
    rkeys = {k: v for k, v in rt.items() if k.startswith("r_")}
    fun = {k[2:]: v for k, v in rt.items() if k.startswith(("f_L", "f_S"))}
    core = {k: v for k, v in fun.items() if k in (
        "L_fills", "S_fills", "L_size_skips", "S_size_skips")}
    print(f"--- {tag}")
    print(" cloud:", json.dumps({k: v for k, v in stats.items() if k in ('Net Profit', 'Drawdown', 'Total Orders', 'Fees')}))
    print(" R:", json.dumps(dict(sorted(rkeys.items()))))
    print(" fills/skips:", json.dumps(core, sort_keys=True))


summarize("E05 midpoint", "e05_out.txt")
summarize("E06 target1.5R", "e06_out.txt")
