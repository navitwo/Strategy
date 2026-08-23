import sys
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
from qc_api import read_files, create_file, update_file, compile_create, poll_compile

PID = 35506697
src = open(r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy\scifvg_main.py").read()

remote = read_files(PID)
print("remote files:", list(remote.keys()))
if "main.py" not in remote:
    create_file(PID, "main.py", src)
    print("created main.py")
elif (remote["main.py"] or "").strip() != src.strip():
    update_file(PID, "main.py", src)
    print("updated main.py")
else:
    print("main.py unchanged")

c = compile_create(PID)
print("compile:", c["compile_id"])
r = poll_compile(PID, c["compile_id"], max_wait=300)
print("compile result ok:", r.get("ok"), "state:", r.get("state"))
if not r.get("ok"):
    print("LOGS:", r.get("logs", "")[:3000])
