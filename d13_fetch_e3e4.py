import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request

PID = 35506697
for name, bid, out in (("E03", None, "e03_out.txt"), ("E04", None, "e04_out.txt")):
    txt = open(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy" + "\\" + out).read()
    bid = None
    for line in txt.splitlines():
        if line.startswith("submitted:"):
            bid = line.split(":", 1)[1].strip()
    d = request("backtests/read", {"projectId": PID, "backtestId": bid})
    bt = d.get("backtest", d)
    rt = bt.get("runtimeStatistics") or {}
    stats = bt.get("statistics") or {}
    rkeys = {k: v for k, v in rt.items() if not k.startswith(("f_", "d_", "funnel"))}
    fun = {k[2:]: v for k, v in rt.items() if k.startswith(("f_L", "f_S"))}
    core = {k: v for k, v in fun.items() if k in (
        "L_attempts", "L_sweep_ok", "L_cisd_ok", "L_inv_ok", "L_fills",
        "S_attempts", "S_sweep_ok", "S_cisd_ok", "S_inv_ok", "S_fills")}
    print(f"--- {name} ({bid[:12]})")
    print(" cloud:", json.dumps({k: stats.get(k) for k in ('Net Profit', 'Drawdown', 'profit_factor', 'win_rate') if k in stats} or {k2: v for k2, v in stats.items() if k2 in ('Net Profit', 'Drawdown')}))
    print(" R-ledger:", json.dumps({k: rkeys[k] for k in sorted(rkeys) if k.startswith('r_')}, sort_keys=True))
    print(" funnel-core:", json.dumps(core, sort_keys=True))
