"""Permanent ad-hoc verifier for the E19B preflight (promoted to test).

Run:  python verify_e19b_preflight.py
Exit 0 iff all checks pass. This file is COMMITTED — it is no longer a
throwaway; it guards the preflight contract between engine, preregistration,
and analysis tooling.

Checks:
  A. Engine (scifvg_main.py) carries all nine directive fixes statically.
  B. Preregistration anchors outcomes on fixed 0.2R theta; MDE diagnostic-only;
     §5 pools across markets over bias_aligned==True only, never across arms.
  C. e19b_bootstrap.py self-test passes (positive/null/inconclusive fixtures).
  D. Local chronology suite green.
"""
import ast
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


eng_p = os.path.join(ROOT, "scifvg_main.py")
src = open(eng_p, encoding="utf-8").read()
try:
    ast.parse(src)
    ok = True
except SyntaxError:
    ok = False
check("A0 scifvg_main.py parses", ok)

code_only = "\n".join(l.split("#")[0] for l in src.splitlines())

# (1) two-sided arming in events_only + bias_aligned tag; mirrored -side arm gone
check("A1a arming gates bias only outside events_only",
      "if not events_only and self.bias != side:" in code_only)
i = src.find("def _try_arm_attempt")
j = src.find("\n    def ", i + 10)
arm_seg = "\n".join(l.split("#")[0] for l in src[i:j].splitlines())
check("A1b events_only arms through setup path (identical validation)",
      '"bias_aligned":' in arm_seg and 'events_only' in arm_seg
      and "_pending_events" not in arm_seg)
check("A1c no counter twin emission at reclaim",
      '(\"counter\", -side)' not in code_only)

# (2) one event_id per reclaim (seq incremented once per candidate)
k = src.find("_ev_candidates.append({")
blk = src[src.rfind("def _advance_setup", 0, k):k]
check("A2 single shared event_id per reclaim (one inc + one use)",
      blk.count("_ev_seq") == 2 and '"event_id"' in code_only
      and '"cand_id"' not in code_only.split("def on_end_of_algorithm")[0]
      and '"arm":' not in blk)

# (3) instrument spec table with real roots/tick/pv
for tok in ('"ES":', '"YM":', '"RTY":', "SP500_E_MINI", "DOW_30_E_MINI",
            "RUSSELL_2000_E_MINI"):
    check(f"A3 spec table has {tok}", tok in code_only or tok in src)
check("A3b old binary root map gone",
      "MICRO_NASDAQ_100_E_MINI)" not in src.split("INSTRUMENT_SPECS")[-1]
      .split(")")[0])

# (4) bps normalization params + helpers
for tok in ("depth_min_bps", "depth_max_bps", "stop_buffer_bps",
            "_depth_thresholds", "_stop_buffer"):
    check(f"A4 {tok} present", tok in code_only)

# (5) excursion-cumulative depth enforcement
check("A5 excursion depth kill in SWEPT extension",
      "excursion_depth_kills" in code_only and
      "exc > dmax" in code_only.replace("&gt;", ">"))

# (6) wall-clock horizon resolution
check("A6 elapsed-minutes resolver",
      "_elapsed_min" in code_only and
      "dt_bars >= h // 5" not in code_only)

# (7) ObjectStore ledger export
check("A7 object_store export", "_export_ledgers" in code_only and
      "object_store.save_bytes" in code_only and
      'self.Debug("TRADE "' not in code_only)

# (8) shadow labels attached to candidates
check("A8 shadow CISD/FVG/IFVG labels",
      all(t in code_only for t in ("shadow_cisd", "shadow_fvg",
                                   "shadow_ifvg", "_shadow_labels")))

# (9a) fill-based economics with barrier-pure r_gross retained
check("A9a r_fill drives usd_net; r_gross retained",
      "r_fill = ((fill_px" in code_only and
      "usd_net = r_fill * self.risk_dist * pv_qty" in code_only and
      '"r_gross"' in src)
# (9b) rollover flatten no longer prices off held quantity
rol_i = src.find('tag="ROLLOVER-FLATTEN"')
rol_blk = src[max(0, rol_i - 700):rol_i]
check("A9b rollover mark not (_m or held)", "(_m or held)" not in rol_blk)

# ---- B. preregistration ----
pr = open(os.path.join(ROOT, "PREREGISTRATION_E19B.md"), encoding="utf-8").read()
check("B1 outcome rule anchored on fixed theta",
      "CI lower bound for Δ exceeds 0.2R" in pr and
      "upper bound for Δ falls below 0.2R" in pr)
check("B2 MDE demoted to power diagnostic",
      "PRE-RUN POWER DIAGNOSTIC ONLY" in pr)
check("B3 pooled defined: markets x bias_aligned only, never arms",
      "POOLED ACROSS MARKETS over rows where bias_aligned == True" in pr
      and "never pooled across arms" in pr)

# ---- C. bootstrap selftest ----
r = subprocess.run([sys.executable, os.path.join(ROOT, "e19b_bootstrap.py"),
                    "--selftest"], capture_output=True, text=True,
                   cwd=ROOT, timeout=300)
check("C1 bootstrap selftest PASS", r.returncode == 0)

# ---- D. local suite ----
r2 = subprocess.run([sys.executable, "-u", "test_scifvg_local.py"],
                    capture_output=True, text=True, cwd=ROOT, timeout=180)
check("D1 local chronology suite green",
      r2.returncode == 0 and "ALL LOCAL CHRONOLOGY TESTS PASSED"
      in r2.stdout)

print("-" * 50)
print(f"PREFLIGHT VERIFIER: {'PASS' if not FAILS else 'FAIL'} "
      f"({len(FAILS)} failure(s))")
for f_ in FAILS:
    print("  failed:", f_)
sys.exit(0 if not FAILS else 1)
