"""Standard experiment runner.

Usage: python run_exp.py "<NAME>" '<json-params>'
- Duplicate-safe: refuses if a backtest with the same name already exists remotely.
- Polls to terminal state, extracts statistics + funnel, appends to experiment_log.jsonl.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
from qc_api import backtest_list, backtest_create, poll_backtest

PID = 35506697
COMPILE = open(ROOT + r"\compile_id.txt").read().strip()

name = sys.argv[1]
params = json.loads(sys.argv[2])

# duplicate rejection
for b in backtest_list(PID):
    if b["name"] == name:
        print(f"DUPLICATE REJECTED: {name} exists ({b['backtest_id']}, {b['status']})")
        sys.exit(2)

bt = backtest_create(PID, name, params, compile_id=COMPILE)
bid = bt["backtest_id"]
print("submitted:", bid)
res = poll_backtest(PID, bid, max_wait=3000, poll_s=12)
status = res.get("status")
if status in ("RuntimeError", "poll-timeout"):
    print("RUN FAILED:", status)
    print(str(res.get("error"))[:600])
    rec = {"name": name, "backtest_id": bid, "params": params,
           "outcome": status, "error": str(res.get("error"))[:400]}
    with open(ROOT + r"\experiment_log.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    sys.exit(1)

stats = res.get("statistics") or {}
tp = (res.get("totalPerformance") or {})
tstat = (tp.get("tradeStatistics") or {})
pstat = (tp.get("portfolioStatistics") or {})
rt = res.get("runtimeStatistics") or {}
fun = {k[2:]: int(v) for k, v in rt.items() if k.startswith("f_")}
diag = {k[2:]: v for k, v in rt.items() if k.startswith("d_")}
local = json.loads(rt.get("local_summary", "{}")) if rt.get("local_summary") else {}

rec = {
    "name": name, "backtest_id": bid, "params": params, "outcome": "Completed",
    "cloud": {
        "trades": stats.get("Trades"), "net_profit": stats.get("Net Profit"),
        "sharpe": stats.get("Sharpe Ratio"), "drawdown": stats.get("Drawdown"),
        "total_orders": stats.get("Total Orders"),
        "fees": tstat.get("totalFees"),
        "win_rate": tstat.get("winRate"),
        "profit_factor": tstat.get("profitFactor"),
        "avg_win": tstat.get("averageWinRate") or tstat.get("averageWin"),
        "avg_loss": tstat.get("averageLossRate") or tstat.get("averageLoss"),
    },
    "funnel": fun, "diag": diag, "local_r": local,
}
with open(ROOT + r"\experiment_log.jsonl", "a") as f:
    f.write(json.dumps(rec) + "\n")
print("COMPLETED")
print("cloud stats:", json.dumps(rec["cloud"]))
print("funnel:", json.dumps(fun, sort_keys=True))
