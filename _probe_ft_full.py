import sys, os, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
os.chdir(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import compile_create, backtest_create, poll_backtest, chart_read, request
cid = open("compile_id.txt").read().strip()
params = {"start_date": "2024-01-01", "end_date": "2024-12-31",
          "run_segment": "dev", "instrument": "NQ",
          "risk_usd": "10000", "max_contracts": "1",
          "variant": "events_only",
          "min_stop_ticks": "8", "floor_atr_frac": "0.10"}
r = backtest_create(35506697, "FT-PROBE-NQ", params, compile_id=cid)
res = poll_backtest(35506697, r["backtest_id"], max_wait=1800, poll_s=10)
d = request("backtests/read", {"projectId": 35506697,
                               "backtestId": r["backtestId" ] if False else r["backtest_id"]})
ch = d["backtest"]["charts"].get("E19B-h120", {})
print("SERIES:", sorted(ch.get("series", {}).keys()))
dd = chart_read(35506697, r["backtest_id"], "E19B-h120")
s = dd.get("chart", {}).get("series", {})
fta = s.get("fta-a", {}).get("values", [])
print("fta-a points:", len(fta), fta[:2] if fta else "")
