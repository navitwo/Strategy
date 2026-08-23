import sys, json, subprocess
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"

# 1) local chronology tests
r = subprocess.run([sys.executable, "test_scifvg_local.py"], capture_output=True, text=True, cwd=ROOT)
print("LOCAL TESTS:", r.stdout.strip().splitlines()[-1] if r.returncode == 0 else "FAILED")
if r.returncode != 0:
    print(r.stderr[-1500:])
    sys.exit(1)

from qc_api import sync_file, compile_create, poll_compile, backtest_create, poll_backtest

PID = 35506697
src = open(ROOT + r"\scifvg_main.py").read()
st = sync_file(PID, "main.py", src)
print("sync:", st)

c = compile_create(PID)
print("compile:", c["compile_id"][:16], "...")
cr = poll_compile(PID, c["compile_id"], max_wait=300)
print("compile ok:", cr.get("ok"), cr.get("state"))
if not cr.get("ok"):
    print(cr.get("logs", "")[:2500])
    sys.exit(1)

NAME = "DIAG-SCIFVG-probe-v2"
params = {"start_date": "2024-06-03", "end_date": "2024-06-14", "run_segment": "full"}
bt = backtest_create(PID, NAME, params, compile_id=c["compile_id"])
print("probe submitted:", bt["backtest_id"])
res = poll_backtest(PID, bt["backtest_id"], max_wait=2400, poll_s=12)
if res.get("status") in ("RuntimeError", "poll-timeout", "Aborted", "Deleted"):
    print("PROBE FAILED:", res.get("status"))
    print(str(res.get("error"))[:800])
    sys.exit(1)
stats = res.get("statistics") or {}
rt = res.get("runtimeStatistics") or {}
print("PROBE COMPLETED")
print("equity:", stats.get("Equity") or rt.get("Equity"), "| orders:", stats.get("Total Orders"))

with open(ROOT + r"\probe_result.json", "w") as f:
    json.dump({"id": bt["backtest_id"], "name": NAME, "status": "Completed",
               "stats": stats, "runtime": rt}, f, indent=2)
with open(ROOT + r"\probe_backtest_id.txt", "w") as f:
    f.write(bt["backtest_id"])
print("saved probe artifacts")
