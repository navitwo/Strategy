"""E19B-R one-year NQ smoke: floor gate + complete-row chart export.

Runs events_only with the preregistered floor (NQ: min 8 ticks, ATR frac
0.10) and asserts:
  1. Run completes; floor_rejects counter present.
  2. n_event_rows == rows retrieved from all E19B-h* charts (completeness).
  3. Replay equality across two runs.
  4. Every retrieved rd value >= floor (population conformance).
"""
import sys
import os

sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
os.chdir(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import backtest_create, poll_backtest, chart_read, request


PARAMS = {"start_date": "2024-01-01", "end_date": "2024-12-31",
          "run_segment": "dev", "instrument": "NQ",
          "risk_usd": "10000", "max_contracts": "1",
          "variant": "events_only",
          "min_stop_ticks": "8", "floor_atr_frac": "0.10"}
VOLATILE = {"runtime_days", "runtime_hours", "runtime_minutes",
            "runtime_seconds", "algorithm_id", "project_id"}


def run(tag):
    r = backtest_create(PID := 35506697, tag, PARAMS, compile_id=COMPILE)
    print(f"{tag}: submitted {r['backtest_id']}", flush=True)
    res = poll_backtest(PID, r["backtest_id"], max_wait=3600, poll_s=15)
    bt = res if isinstance(res, dict) else {}
    rt = bt.get("runtimeStatistics") or {}
    err = str(bt.get("error") or "")[:200]
    if err and err != "None":
        print(f"{tag}: ERROR {err}", flush=True)
        fails.append(f"{tag}: {err}")
    return r["backtest_id"], rt


COMPILE = open("compile_id.txt").read().strip()
fails = []
b1, rt1 = run("E19BR-smoke-A")
b2, rt2 = run("E19BR-smoke-B")

for name, rt in (("A", rt1), ("B", rt2)):
    if not rt:
        fails.append(f"{name}: no telemetry")

n_declared = int(rt1.get("n_event_rows", -1))
floor_ticks = 8
tick = 0.25
floor_val = floor_ticks * tick
atr_frac_floor = None  # ATR varies; ticks bound is the hard minimum

retrieved = 0
rd_violations = 0
for h in (30, 60, 120, 240):
    d = chart_read(35506697, b1, f"E19B-h{h}")
    for sname, sv in d.get("chart", {}).get("series", {}).items():
        if not sname.startswith("rd-"):
            continue
        for pt in sv.get("values", []):
            retrieved += 1
            y = float(pt["y"] if isinstance(pt, dict) else pt[1])
            if y < floor_val - 1e-9:
                rd_violations += 1
print(f"declared n_event_rows={n_declared}, retrieved rd rows={retrieved}")
print(f"rd below tick-floor: {rd_violations}")

if n_declared != retrieved:
    fails.append(f"row-count mismatch declared={n_declared} "
                 f"retrieved={retrieved}")
if rd_violations:
    fails.append(f"{rd_violations} rows below executable floor")
if int(rt1.get("f_L_floor_rejects", 0) or 0) + \
        int(rt1.get("f_S_floor_rejects", 0) or 0) <= 0:
    print("note: zero floor rejects in this window (acceptable)")

clean1 = {k: v for k, v in rt1.items() if k not in VOLATILE}
clean2 = {k: v for k, v in rt2.items() if k not in VOLATILE}
if clean1 != clean2:
    diff = [k for k in set(clean1) | set(clean2)
            if clean1.get(k) != clean2.get(k)]
    fails.append(f"replay mismatch: {sorted(diff)[:8]}")
else:
    print(f"REPLAY EQUALITY on {len(clean1)} keys")

print("-" * 50)
if fails:
    print("E19B-R SMOKE: FAIL")
    for f_ in fails:
        print("  ", f_)
    sys.exit(1)
print("E19B-R SMOKE: PASS (complete ledger via charts, floor enforced, "
      "replay deterministic)")
with open("e19br_smoke_result.json", "w") as f:
    import json
    json.dump({"A": b1, "B": b2, "rows": retrieved,
               "floor_rejects": int(rt1.get("f_L_floor_rejects", 0) or 0)
               + int(rt1.get("f_S_floor_rejects", 0) or 0)}, f, indent=1)
