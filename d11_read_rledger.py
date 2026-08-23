import json
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
for f in ("e01d_out.txt", "e02_out.txt"):
    txt = open(ROOT + "\\" + f).read()
    for line in txt.splitlines():
        if line.startswith("funnel:"):
            fun = json.loads(line[7:].strip())
            keys = [k for k in fun if k.startswith("r_")]
            print(f, {k: fun[k] for k in sorted(keys)})
