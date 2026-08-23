"""RED/GREEN repro: real on_data must aggregate 20 minute bars into 4 x 5m.

Drives SweepCisdIfvgAlgorithm.on_data directly with synthetic TradeBar-like
objects (real entry point, no stubs). RED on the pre-fix commit (unconditional
trailing flush emits one 5m-shaped bar per minute). GREEN after the fix.
"""
import sys
import types
from datetime import datetime, timedelta, timezone

ROOT = r"C:\Users\Jostb\OneDrive\Documents\Hermes Projects\Strategy"
sys.path.insert(0, ROOT)

stub_src = (
    "class QCAlgorithm: pass\n"
    "class FeeModel: pass\n"
    "class OrderFee: pass\n"
    "class CashAmount: pass\n"
    "class OrderStatus:\n"
    "    SUBMITTED=101; FILLED=102; CANCELED=103; CANCEL_PENDING=104; INVALID=105\n"
)

mod = types.ModuleType("scifvg_real")
mod.__dict__["timedelta"] = timedelta


class _Sym:
    def __init__(self, v):
        self.value = v

    def __eq__(self, o):
        return isinstance(o, _Sym) and o.value == self.value

    def __hash__(self):
        return hash(self.value)

    def __str__(self):
        return self.value


class _Bar:
    def __init__(self, o, h, l, c, end_dt):
        self.open, self.high, self.low, self.close = o, h, l, c
        self.end_time = end_dt


class _Data:
    def __init__(self, pairs):
        self.bars = dict(pairs)


class _Fut:
    def __init__(self):
        self.symbol = _Sym("MNQ")
        self.mapped = _Sym("MNQZ24")


exec(compile(stub_src, "<stubs>", "exec"), mod.__dict__)
src = open(ROOT + r"\scifvg_main.py", encoding="utf-8").read()
src = src.replace("from AlgorithmImports import *", "")
exec(compile(src, "scifvg_main.py", "exec"), mod.__dict__)

Alg = mod.SweepCisdIfvgAlgorithm


def make_alg():
    a = Alg.__new__(Alg)
    a.fun = {k: 0 for k in mod.FUNNEL_KEYS}
    a.cfg = {"pivot_lookback": 3, "pivot_right": 3,
             "fvg_min_ticks": 4, "fvg_max_age_bars": 60}
    a.tick = 0.25
    a.ny = timezone(timedelta(hours=-5))
    a.fut = _Fut()
    a.acc5 = []
    a.acc5_key = None
    a.bars5 = []
    a.h4_pub = []
    a.h4_bucket = None
    a.h4_min_span_min = 210
    a.h4_max_offset0 = 1
    a.h4_gap_pending = False
    a.swing_hi = []
    a.swing_lo = []
    a.bias = 0
    a.setup = None
    a.cur_session = None
    a.pdh = None
    a.pdl = None
    a.cur_high = None
    a.cur_low = None
    a.session_tried = set()
    a.last_mapped = None
    a.pos_qty = 0
    a._eq_at_entry = None
    a.camp_start = datetime(2024, 6, 4).date()
    a.w_start = 9 * 60 + 30
    a.w_end = 12 * 60
    a.stop_ticket = None
    a.tp_ticket = None
    a.entry_ticket = None

    def noop(*args, **kwargs):
        pass
    a.market_order = noop
    return a


def feed(a, start_utc, n_minutes):
    t0 = start_utc.replace(second=0, microsecond=0)
    for k in range(n_minutes):
        end = t0 + timedelta(minutes=k + 1)
        bar = _Bar(100.0, 100.5, 99.5, 100.2, end)
        a.on_data(_Data([(_Sym("MNQ"), bar)]))
    return list(a.bars5)


def main():
    start = datetime(2024, 6, 4, 14, 0, tzinfo=timezone.utc)
    a = make_alg()
    out = feed(a, start, 20)

    ok = True
    if len(out) != 4:
        print(f"FAIL expected exactly 4 aggregated 5m bars, got {len(out)}")
        ok = False
    else:
        print("PASS 20 minute bars -> 4 x 5m bars")
    if len(out) == 4:
        want = [(9, m) for m in (5, 10, 15, 20)]
        got = [(b["et"].hour, b["et"].minute) for b in out]
        aligned = got == want
        print(("PASS" if aligned else "FAIL") + " slots align to :05..:20 ET")
        ok = ok and aligned
    before = len(a.bars5)
    a.on_data(_Data([]))
    if len(a.bars5) != before:
        print("FAIL trailing empty slice emitted extra aggregation(s)")
        ok = False
    else:
        print("PASS trailing empty slice emits nothing")
    print("REPRO RESULT:", "GREEN" if ok else "RED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
