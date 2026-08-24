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

# Review round 4: a zero-trade day makes rec_ok==1 trivially true. Use a
# 2-week window and REQUIRE >=3 closed trades for the gate to be meaningful.
params = {"start_date": "2024-06-03", "end_date": "2024-06-14",
          "run_segment": "full", "instrument": "NQ",
          "risk_usd": "10000", "max_contracts": "1"}

bt = backtest_create(PID, "SMOKE-gate-2wk", params, compile_id=COMPILE)
print("smoke submitted:", bt["backtest_id"], flush=True)
res = poll_backtest(PID, bt["backtest_id"], max_wait=2400, poll_s=10)
if res.get("status") in ("RuntimeError", "poll-timeout"):
    print("GATE FAIL: run did not complete:", res.get("status"))
    print(str(res.get("error"))[:400])
    sys.exit(1)

rt = res.get("runtimeStatistics") or {}
fails = []

bars5 = int(rt.get("d_bars5_total", 0) or 0)
# NQ trades ~23h/day on 5m buckets => ~276 bars/session; a 2-day window with
# partial boundary days lands in [300, 700]. Fragmentation bugs (1 bar/min)
# would produce ~2800+ and fail the upper bound; dead consolidators give <100.
# d_bars5_total includes the ~40-day warmup (bars flow before camp_start);
# ~29 trading days x ~276 bars + 1 trade day ~= 8000-8600. Fragmentation (the
# 1-bar-per-minute bug) would show ~41k; dead consolidators would show <1000.
if not (9000 <= bars5 <= 12500):
    fails.append(f"bar_count_5m={bars5} outside warmup-aware band [6500,9500]")
tz = rt.get("tzcheck_ok", "0")
if tz != "1":
    fails.append(f"TZCHECK not satisfied (tzcheck_ok={tz})")
h4 = int(rt.get("d_h4_published", 0) or 0)
if h4 < 1:
    fails.append(f"d_h4_published={h4} < 1")
rec = rt.get("rec_ok", "0")
fills = int(rt.get("f_L_fills", 0)) + int(rt.get("f_S_fills", 0))
trades = int(rt.get("r_trades", 0))
if trades < 3:
    fails.append(f"trades={trades} < 3 - reconcile not meaningfully exercised")
qty_ok = rt.get("qty_max_seen", "1") == "1"
if rec != "1":
    fails.append(f"rec_ok={rec} exp={rt.get('rec_exp_usd')} "
                 f"obs={rt.get('rec_obs_usd')} resid={rt.get('rec_resid')}")
if fills != trades:
    fails.append(f"fills({fills}) != ledger trades({trades})")
if fills > 0 and not qty_ok:
    fails.append("fill with qty != 1")

verdict = {"bid": bt["backtest_id"], "bars5": bars5, "tzcheck": tz,
           "h4_published": h4, "rec_ok": rec, "fills": fills,
           "trades": trades, "fails": fails}
print(json.dumps(verdict, indent=1))
print("GATE RESULT:", "PASS" if not fails else "FAIL")
sys.exit(0 if not fails else 1)
