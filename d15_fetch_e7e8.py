import sys
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "d14", r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy\d14_fetch_e5e6.py")
m = importlib.util.module_from_spec(spec)
# prevent module-level summarize calls
src = open(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy\d14_fetch_e5e6.py").read()
exec(compile(src, "d14", "exec"), {"__name__": "x"}) if False else None
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
    core = {k: v for k, v in fun.items() if k in ("L_attempts", "S_attempts",
        "L_sweep_ok", "L_cisd_ok", "L_inv_ok", "L_fills",
        "S_sweep_ok", "S_cisd_ok", "S_inv_ok", "S_fills")}
    print(f"--- {tag}")
    print(" cloud:", {k: v for k, v in stats.items() if k in ('Net Profit', 'Drawdown', 'Total Orders')})
    print(" R:", dict(sorted(rkeys.items())))
    print(" funnel:", json.dumps(core, sort_keys=True) if (json := __import__('json')) else "")


summarize("E07 window 0830-1130", "e07_out.txt")
summarize("E08 window 0930-1300", "e08_out.txt")
