import sys, json, subprocess
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"

r = subprocess.run([sys.executable, "test_scifvg_local.py"], capture_output=True, text=True, cwd=ROOT)
print("LOCAL TESTS:", "OK" if r.returncode == 0 else "FAILED")
if r.returncode != 0:
    sys.exit(1)

from qc_api import sync_file, compile_create, poll_compile, backtest_create, poll_backtest

PID = 35506697
src = open(ROOT + r"\scifvg_main.py").read()
print("sync:", sync_file(PID, "main.py", src))
c = compile_create(PID)
cr = poll_compile(PID, c["compile_id"], max_wait=300)
print("compile ok:", cr.get("ok"))
if not cr.get("ok"):
    print(cr.get("logs", "")[:2000]); sys.exit(1)

NAME = "DIAG-SCIFVG-probe-v3-funnel"
params = {"start_date": "2024-06-03", "end_date": "2024-06-14", "run_segment": "full"}
bt = backtest_create(PID, NAME, params, compile_id=c["compile_id"])
bid = bt["backtest_id"]
print("submitted:", bid)
res = poll_backtest(PID, bid, max_wait=2400, poll_s=12)
if res.get("status") in ("RuntimeError", "poll-timeout"):
    print("FAILED:", res.get("status"), str(res.get("error"))[:500])
    sys.exit(1)
rt = res.get("runtimeStatistics") or {}
fun = {k[2:]: v for k, v in rt.items() if k.startswith("f_")}
diag = {k[2:]: v for k, v in rt.items() if k.startswith("d_")}
print("FUNNEL:", json.dumps(fun, sort_keys=True))
print("DIAG:", json.dumps(diag, sort_keys=True))
with open(ROOT + r"\probe3_result.json", "w") as f:
    json.dump({"id": bid, "rt": rt}, f, indent=2)
