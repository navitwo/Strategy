"""E16e: inversion-stage diagnosis — why do only 13 of 122 CISDs invert?

Counters show CISD ok (122) but inv_ok only 13. The remaining 109 die at
inv_timeout. Hypothesis: with the throttle removed, the eligible-gap scan now
finds gaps whose midpoint is FAR above the CISD close (old, distant zones), so
the 'close beyond midpoint within 12 bars' condition rarely triggers even
though a valid nearer gap exists. The oldest-first selection may be picking
unreachable gaps. Fix candidate: prefer the NEAREST gap to price (smallest
distance from CISD bar close to zone proximal edge) instead of oldest.
"""
import sys, json
sys.path.insert(0, r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy")
ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"

src = open(ROOT + r"\scifvg_main.py").read()
# change selection: nearest-to-price wins rather than oldest-created
old = '''                    if elig is None or g["created"] < elig["created"]:
                        elig = g'''
new = '''                    # nearest-to-price selection (E16e fix): pick the gap
                    # whose proximal edge is closest to the CISD close so the
                    # retest is actually reachable within the deadline window.
                    prox = b["close"] - g["hi"] if side > 0 else g["lo"] - b["close"]
                    if elig is None or prox < elig.setdefault("_prox", 1e18):
                        elig = dict(g)
                        elig["_prox"] = prox'''
assert old in src
src = src.replace(old, new, 1)
open(ROOT + r"\scifvg_main.py", "w").write(src)
print("nearest-gap selection installed")
