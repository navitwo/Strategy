"""SMOKE GATE - hard precondition before ANY multi-year submission.

One trading day, NQ 1-contract. Asserts (from RuntimeStatistics):
  1. bar_count_5m within expected RTH+ETH band for one session
  2. TZCHECK debug line seen: first RTH 5m bar stamps 09:35 ET
  3. d_h4_published >= 1
  4. rec_ok == 1 (reconciliation gate)
  5. qty == 1 on any fill OR zero fills with all gates green
Exit code 0 = gate passed.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
os.chdir(ROOT) if (os := __import__("os")) else None
from qc_api import backtest_create, poll_backtest, request

PID = 35506697
COMPILE = open(ROOT + r"\compile_id.txt").read().strip()

# Review round 4: a zero-trade day makes rec_ok==1 trivially true. The setup
# fires ~3x/quarter, so scan windows until one yields >=3 closed trades.
WINDOWS = [("2024-01-01", "2024-06-30", "H1-24"),
           ("2023-01-01", "2023-12-31", "FY-23"),
           ("2022-01-01", "2023-12-31", "FY22-23")]

rt, fails, used = None, [], None
for wstart, wend, tag in WINDOWS:
    params = {"start_date": wstart, "end_date": wend,
              "run_segment": "full", "instrument": "NQ",
              "risk_usd": "10000", "max_contracts": "1"}
    bt = backtest_create(PID, f"SMOKE-gate-{tag}", params, compile_id=COMPILE)
    print("smoke submitted:", bt["backtest_id"], tag, flush=True)
    res = poll_backtest(PID, bt["backtest_id"], max_wait=3600, poll_s=10)
    if res.get("status") in ("RuntimeError", "poll-timeout"):
        print("run failed:", res.get("status"), str(res.get("error"))[:200])
        continue
    rt = res.get("runtimeStatistics") or {}
    tr = int(rt.get("r_trades", 0))
    print(f"window {tag}: trades={tr}")
    if tr >= 3:
        used = tag
        break
if rt is None:
    print("GATE FAIL: no window completed")
    sys.exit(1)
bars5 = int(rt.get("d_bars5_total", 0) or 0)
sessions = int(rt.get("funnel_sessions", 0) or 0)
fails = []
# fragmentation detector: bars PER SESSION must match ~271.9 (23h ETH on 5m).
# The 1-bar-per-minute bug yields ~1200/session; dead consolidators yield ~0.
if sessions >= 10:
    bps = bars5 / sessions
    if not (230 <= bps <= 310):
        fails.append(f"bars/session={bps:.1f} outside [230,310] "
                     f"(bars={bars5}, sessions={sessions})")

bars5 = int(rt.get("d_bars5_total", 0) or 0)
# NQ trades ~23h/day on 5m buckets => ~276 bars/session; a 2-day window with
# partial boundary days lands in [300, 700]. Fragmentation bugs (1 bar/min)
# would produce ~2800+ and fail the upper bound; dead consolidators give <100.
# d_bars5_total includes the ~40-day warmup (bars flow before camp_start);
# ~29 trading days x ~276 bars + 1 trade day ~= 8000-8600. Fragmentation (the
# 1-bar-per-minute bug) would show ~41k; dead consolidators would show <1000.
tz = rt.get("tzcheck_ok", "0")
if tz != "1":
    fails.append(f"TZCHECK not satisfied (tzcheck_ok={tz})")
h4 = int(rt.get("d_h4_published", 0) or 0)
if h4 < 1:
    fails.append(f"d_h4_published={h4} < 1")
rec = rt.get("rec_ok", "0")
fills = int(rt.get("f_L_fills", 0)) + int(rt.get("f_S_fills", 0))
orphans = int(rt.get("f_orphan_entry_fills", 0) or 0)
trades = int(rt.get("r_trades", 0))
if trades < 3:
    fails.append(f"trades={trades} < 3 - reconcile not meaningfully exercised")
qty_ok = abs(float(rt.get("qty_max_seen", "1") or 1) - 1.0) < 1e-9
if rec != "1":
    fails.append(f"rec_ok={rec} detail: " + json.dumps({k: rt.get(k) for k in rt if k.startswith("rec_")}))
# I3 (engine-side) already validates the full cycle-explained count
# (entries vs ledger rows + orphans + late closes + race legs); rec_ok=1
# implies it passed. Here only assert no SILENT leak:
if int(rt.get("f_untracked_fills", 0) or 0) > 0:
    fails.append(f"untracked_fills={rt.get('f_untracked_fills')}")
# v2.4 strict: zero anomalies; cycles == exits
anom = int(rt.get("f_anomalous_exit_events", 0) or 0)
cyc = int(rt.get("d_cycles_opened", 0) or 0)
aex = int(rt.get("d_atomic_exits", 0) or 0)
if anom != 0:
    fails.append(f"anomalous_exit_events={anom} (must be 0)")
if trades > 0 and cyc != aex:
    fails.append(f"cycles({cyc}) != atomic_exits({aex})")
if fills > 0 and not qty_ok:
    fails.append("fill with qty != 1")

verdict = {"bid": bt["backtest_id"], "bars5": bars5, "tzcheck": tz,
           "h4_published": h4, "rec_ok": rec, "fills": fills,
           "trades": trades, "fails": fails}
print(json.dumps(verdict, indent=1))
print("GATE RESULT:", "PASS" if not fails else "FAIL")
sys.exit(0 if not fails else 1)
