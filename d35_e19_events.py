"""E19: HTF-bias + sweep/reclaim EVENT STUDY (no entry, no gates).

Question per review-round-5 directive: does the HTF-bias + sweep/reclaim
signal family contain ANY forward directional information on NQ?

Method:
- Run the candidate engine over dev period; it emits SWEEP-ARM events
  (attempt armed: price swept PDH/PDL with bias aligned).
- For each event, the engine logs a DEBUG line:
    EVENT {"t": <bar_end_et>, "side": +/-1, "extreme": px, "level": px}
- Offline: for each event, compute forward returns over horizons
  {30m, 1h, 2h, 4h, EOD} from event close using minute data exported by
  MINUTE lines; then block-bootstrap (block=1 day) CIs for mean forward
  return vs zero, separately for long-side and short-side events.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
import os; os.chdir(ROOT)
from qc_api import backtest_create, poll_backtest

PID = 35506697
COMPILE = open(ROOT + r"\compile_id.txt").read().strip()

# The engine needs an "events_only" variant: arm attempts and log them, but
# never submit entries. Check whether scifvg_main supports it via variant
# "events_only" - if not, this driver fails fast and the engine must be
# patched first.
params = {"start_date": "2010-01-01", "end_date": "2024-12-31",
          "run_segment": "full", "instrument": "NQ",
          "risk_usd": "10000", "max_contracts": "1",
          "variant": "events_only"}

r = backtest_create(PID, "E19-event-study", params, compile_id=COMPILE)
print("submitted E19:", r["backtest_id"], flush=True)
res = poll_backtest(PID, r["backtest_id"], max_wait=3600, poll_s=15)
rt = res.get("runtimeStatistics") or {}
print("status:", res.get("status"))
keep = ("r_trades", "rec_ok", "f_L_attempts", "f_S_attempts",
        "f_L_sweep_ok", "f_S_sweep_ok", "d_events_logged",
        "d_minutes_logged")
print(json.dumps({k: rt.get(k) for k in keep}, indent=1))
with open(ROOT + r"\e19_results.jsonl", "a") as f:
    f.write(json.dumps({"bid": r["backtest_id"],
                        "rt": {k: str(v) for k, v in rt.items()}}) + "\n")
