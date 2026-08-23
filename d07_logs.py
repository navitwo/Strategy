import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request

PID = 35506697
BID = open(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy\probe_backtest_id.txt").read().strip()
print("probe id:", BID)

d = request("backtests/read", {"projectId": PID, "backtestId": BID})
bt = d.get("backtest", d)
print("runtimeStatistics:", json.dumps(bt.get("runtimeStatistics") or {})[:800])

# try log endpoints
for ep, payload in (("backtests/log/read", {"projectId": PID, "backtestId": BID}),
                    ("backtests/logs/read", {"projectId": PID, "backtestId": BID})):
    try:
        r = request(ep, payload)
        s = json.dumps(r, default=str)
        print(f"--- {ep}: keys={sorted(r.keys()) if isinstance(r, dict) else type(r)}")
        print(s[:1200])
        break
    except Exception as e:
        print(f"--- {ep} failed: {str(e)[:200]}")
