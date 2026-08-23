"""Diagnose zero-attempt regression in v2.0: check 4H bucket coverage.

The full-coverage gate (48/48 minutes) may be impossible to satisfy because
LEAN minute bars only exist where trades occurred — quiet overnight stretches
have gaps. Count published buckets and their bar counts by instrumenting a
short cloud run with per-bucket diagnostics via RuntimeStatistics.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"

src = open(ROOT + r"\scifvg_main.py").read()

# temporary instrumentation: publish bucket-size histogram at end
needle = 'self.RuntimeStatistics["rollovers"] = str(self.fun.get("rollovers", 0))'
assert needle in src
add = '''
            self.RuntimeStatistics["d_bucket_hist"] = json.dumps(
                dict(sorted(Counter(self._bucket_sizes).items())), sort_keys=True)
            self.RuntimeStatistics["d_bias_final"] = str(self.bias)
            self.RuntimeStatistics["d_pdh_none_days"] = str(self.fun.get("no_prior_levels", 0))
'''
src2 = src.replace(needle, needle + add, 1)

# also record bucket sizes on publish
n1 = '        idx = len(self.h4_pub)\n'
assert n1 in src2
src2 = src2.replace(n1,
    '        self._bucket_sizes.append(len(bars))\n' + n1, 1)
src2 = src2.replace('from zoneinfo import ZoneInfo',
                    'from zoneinfo import ZoneInfo\nfrom collections import Counter', 1)
src2 = src2.replace("        self.h4_gap_pending = False\n",
                    "        self.h4_gap_pending = False\n        self._bucket_sizes = []\n", 1)
open(ROOT + r"\scifvg_diag_main.py", "w").write(src2)
print("instrumented copy written")

# upload as separate file in same project? No - use files/update of research file
from qc_api import read_files, create_file, update_file, compile_create, poll_compile, backtest_create, poll_backtest
PID = 35506697
remote = read_files(PID)
if "diag_bucket_main.py" in remote:
    update_file(PID, "diag_bucket_main.py", src2)
else:
    create_file(PID, "diag_bucket_main.py", src2)
c = compile_create(PID)
cr = poll_compile(PID, c["compile_id"], max_wait=300)
print("compile ok:", cr.get("ok"))
if not cr.get("ok"):
    print(cr.get("logs", "")[:1500]); sys.exit(1)
params = {"start_date": "2024-06-03", "end_date": "2024-08-30", "run_segment": "full",
          "invert_on_cisd_bar": "1"}
bt = backtest_create(PID, "DIAG-v2-bucket-coverage", params, compile_id=c["compile_id"])
print("submitted:", bt["backtest_id"])
res = poll_backtest(PID, bt["backtest_id"], max_wait=2400, poll_s=12)
if res.get("status") in ("RuntimeError", "poll-timeout"):
    print("FAILED:", res.get("status"), str(res.get("error"))[:400]); sys.exit(1)
rt = res.get("runtimeStatistics") or {}
print("h4_published:", rt.get("d_h4_published"))
print("bucket_hist:", rt.get("d_bucket_hist"))
print("bias_final:", rt.get("d_bias_final"))
print("r_trades:", rt.get("r_trades"), "| L_attempts:", rt.get("f_L_attempts"))
