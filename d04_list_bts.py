import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import backtest_list

PID = 35506697
bts = backtest_list(PID)
for b in bts:
    print(b)
