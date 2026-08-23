import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
from qc_api import sync_file, compile_create, poll_compile

PID = 35506697
src = open(ROOT + r"\scifvg_main.py").read()
st = sync_file(PID, "main.py", src)
c = compile_create(PID)
cr = poll_compile(PID, c["compile_id"], max_wait=300)
print("sync:", st, "| compile ok:", cr.get("ok"), cr.get("state"))
if not cr.get("ok"):
    print(cr.get("logs", "")[:2500])
    sys.exit(1)
open(ROOT + r"\compile_id.txt", "w").write(c["compile_id"])
print("compile id saved:", c["compile_id"][:20], "...")
