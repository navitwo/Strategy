"""B2-E15: Gate-contribution study vs random-entry null.

For each gate configuration, run the strategy AND a matched random-entry
generator that samples the same number of entries from the same eligible
bar population (same window, same side balance, same stop/target geometry,
same costs). Emits per-run ledgers as JSON lines for offline pandas analysis.

Random-entry mode: parameter entry_mode=random uses algorithm-time hashing
(deterministic given exp_hash) to decide at each eligible completed 5m bar,
flat + in-window + levels known, whether to open a trade with the SAME
stop/target construction (sweep-extreme or gap-far per stop_mode) and sizing.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"

src = open(ROOT + r"\scifvg_main.py").read()

# ---- inject random-entry engine ----
marker = "    # ---------------------------------------------------------- state machine"
assert marker in src

random_engine = '''
    # ---------------------------------------------------- random-entry null
    def _maybe_random_entry(self, b, idx, et):
        """Deterministic pseudo-random entry for the null distribution.

        Eligible: flat, no setup, in window, levels known. Probability tuned so
        expected trade count roughly matches the strategy's, but the sequence is
        independent of signal logic. Same bracket geometry and sizing.
        """
        import hashlib as _h
        if not self._in_window(et) or not self._new_setup_allowed():
            return
        p = float(self.cfg.get("random_entry_prob", "0.02"))
        seed = f"{self.exp_hash}|{b['et'].isoformat()}"
        h = int(_h.md5(seed.encode()).hexdigest()[:8], 16)
        if (h % 10000) / 10000.0 >= p:
            return
        side = 1 if (h % 2 == 0) else -1
        level = self.pdl if side > 0 else self.pdh
        ext = b["low"] if side > 0 else b["high"]
        mid = (level + ext) / 2.0
        g = {"lo": min(level, ext), "hi": max(level, ext)}
        s = {
            "side": side, "stage": "PENDING", "arm_sk": self._session_key(et),
            "b0": idx, "reclaim_deadline": idx, "level": level,
            "extreme": ext, "extreme_idx": idx, "ref_open": None,
            "ref_idx": None, "cisd_deadline": idx, "fvg": g,
            "inv_deadline": idx, "cisd_idx": idx,
            "retest_deadline": idx + self.cfg["retest_max_bars"],
            "entry_id": None,
        }
        self.setup = s
        self._submit_entry(s, idx)
        K = self._sk(side)
        self._inc(f"{K}_attempts")

'''
src = src.replace(marker, random_engine + marker, 1)

# expose the null-mode parameters through the canonical whitelist
old_wl = '''                  "pivot_lookback", "pivot_right", "max_attempts_per_day",
                  "stop_mode"):'''
new_wl = '''                  "pivot_lookback", "pivot_right", "max_attempts_per_day",
                  "stop_mode", "entry_mode", "random_entry_prob"):'''
assert old_wl in src
src = src.replace(old_wl, new_wl, 1)
old_def = '''            "max_attempts_per_day": 1, "stop_mode": "sweep",
        }'''
new_def = '''            "max_attempts_per_day": 1, "stop_mode": "sweep",
            "entry_mode": "signal", "random_entry_prob": 0.02,
        }'''
assert old_def in src
src = src.replace(old_def, new_def, 1)

# call site already patched directly in scifvg_main.py (entry_mode dispatch)
assert '_maybe_random_entry(b, idx, et)' in src, "random call site missing"

# export per-trade ledger at end
old_end = '        self.Debug("FUNNEL " + json.dumps(self.fun, sort_keys=True))'
assert old_end in src
ledger_export = '''        self.Debug("TRADES " + json.dumps({
            "exp_hash": self.exp_hash, "cfg": {k: self.cfg[k] for k in sorted(self.cfg)},
            "trades": [
                {"r": t["r"], "risk_dist": t["risk_dist"], "qty": t["qty"],
                 "obs_usd": t["obs_usd"]} for t in self.trade_economics
            ],
        }))
''' + old_end
src = src.replace(old_end, ledger_export, 1)

open(ROOT + r"\scifvg_null_main.py", "w").write(src)
print("null-engine variant written")

from qc_api import create_file, update_file, read_files, compile_create, poll_compile, backtest_create, poll_backtest
PID = 35506697
remote = read_files(PID)
name = "null_main.py"
if name in remote:
    update_file(PID, name, src)
else:
    create_file(PID, name, src)
c = compile_create(PID)
cr = poll_compile(PID, c["compile_id"], max_wait=300)
print("compile ok:", cr.get("ok"), cr.get("state"))
if not cr.get("ok"):
    print(cr.get("logs", "")[:2000]); sys.exit(1)
open(ROOT + r"\compile_id.txt", "w").write(c["compile_id"])
print("NOTE: compile_id.txt now points at NULL build — flip main.py back before signal runs")

# quick smoke: one random run over 2024 H2
params = {"start_date": "2024-06-03", "end_date": "2024-12-31",
          "run_segment": "full", "invert_on_cisd_bar": "1",
          "entry_mode": "random", "random_entry_prob": "0.01"}
bt = backtest_create(PID, "NULL-smoke-random-v1", params, compile_id=c["compile_id"])
print("submitted:", bt["backtest_id"])
res = poll_backtest(PID, bt["backtest_id"], max_wait=2400, poll_s=12)
if res.get("status") in ("RuntimeError", "poll-timeout"):
    print("FAILED:", res.get("status"), str(res.get("error"))[:400]); sys.exit(1)
rt = res.get("runtimeStatistics") or {}
print({k: rt.get(k) for k in ("r_trades", "r_wins", "r_avg", "r_sum", "rec_ok")})
