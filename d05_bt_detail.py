import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import request

PID = 35506697
BID = "d071c60c7291a3d3af549e42087b4fdc"
d = request("backtests/read", {"projectId": PID, "backtestId": BID})
print("top keys:", sorted(d.keys()) if isinstance(d, dict) else type(d))
print(json.dumps(d, default=str)[:2000])
