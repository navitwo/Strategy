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
        if line.startswith("RUN FAILED"):
            print(f"--- {tag}: RUN FAILED")
            print(txt[:800])
            return
    d = request("backtests/read", {"projectId": PID, "backtestId": bid})
    bt = d.get("backtest", d)
    rt = bt.get("runtimeStatistics") or {}
    stats = bt.get("statistics") or {}
    rkeys = {k: v for k, v in rt.items() if k.startswith("r_")}
    fun = {k[2:]: v for k, v in rt.items() if k.startswith(("f_L", "f_S"))}
    core = {k: v for k, v in fun.items() if k in ("L_attempts", "S_attempts",
        "L_sweep_ok", "L_cisd_ok", "L_inv_ok", "L_fills", "L_size_skips",
        "S_sweep_ok", "S_cisd_ok", "S_inv_ok", "S_fills", "S_size_skips")}
    print(f"--- {tag}")
    print(" cloud:", {k: v for k, v in stats.items() if k in ('Net Profit', 'Drawdown', 'Total Orders', 'Fees')})
    print(" R:", json.dumps(dict(sorted(rkeys.items()))))
    print(" funnel:", json.dumps(core, sort_keys=True))


summarize("E09 sweep_min 8t", "e09_out.txt")
summarize("E10 NQ replication", "e10_out.txt")
