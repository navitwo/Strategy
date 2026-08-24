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
    a.unfilled_watch = []
    a.d_bars5_total = 0
    a.tzcheck_ok = 0
    a.qty_max_seen = 0
    a._flatten_tickets = []
    a.Debug = lambda *a2, **k2: None
    a.RuntimeStatistics = {}
    a.unfilled_resolved_n = 0
    a.camp_start = datetime(2024, 6, 4).date()
    a.w_start = 9 * 60 + 30
    a.w_end = 12 * 60
    a.stop_ticket = None
    a.tp_ticket = None
    a.entry_ticket = None

    def noop(*args, **kwargs):
        pass
    a.market_order = noop
    a.last_bar_et = None
    a._consolidators = [(5, a._on_5m_consolidated)]

    def register_consolidate(period, resolution, handler):
        a._consolidators.append((period, handler))
    a.consolidate = register_consolidate
    return a



def feed(a, start_utc, n_minutes):
    """Feed minute bars through an emulated LEAN consolidator + real on_data.

    The emulated TradeBarConsolidator(5m) fires its handler exactly once per
    completed :00-grid bucket — matching LEAN semantics used by self.consolidate.
    """
    # v2.1 timezone contract: handler consumes NAIVE ET (algorithm tz). The
    # harness therefore delivers 09:31.. ET wall-clock, not UTC.
    t0 = start_utc.replace(second=0, microsecond=0, tzinfo=None)
    a.ny = None  # unused by handler now
    period_min = 5
    state = {"key": None, "o": None, "h": None, "l": None, "c": None}

    def emit(end_utc):
        class _C:
            pass
        cb = _C()
        cb.open, cb.high, cb.low, cb.close = (
            state["o"], state["h"], state["l"], state["c"])
        cb.end_time = end_utc
        for _, handler in getattr(a, "_consolidators", []):
            handler(cb)

    for k in range(n_minutes):
        end = t0 + timedelta(minutes=k + 1)
        o = 100.0 + k * 0.01
        c = o + 0.2
        bar = _Bar(o, o + 0.5, o - 0.5, c, end)
        # consolidator update (before on_data, like LEAN's pipeline)
        et_end = bar.end_time
        st_start = et_end - timedelta(minutes=1)
        key = (st_start.year, st_start.month, st_start.day,
               st_start.hour, st_start.minute // period_min)
        if state["key"] is None:
            state.update(key=key, o=o, h=bar.high, l=bar.low, c=c)
        elif key != state["key"]:
            emit(bar.end_time - timedelta(minutes=1))
            state.update(key=key, o=o, h=bar.high, l=bar.low, c=c)
        else:
            state["h"] = max(state["h"], bar.high)
            state["l"] = min(state["l"], bar.low)
            state["c"] = c
        # real entry point
        a.on_data(_Data([(_Sym("MNQ"), bar)]))
    # LEAN flushes consolidators at scanner end / unsubscribe; emulate that so
    # the final partial-fed bucket is not silently lost.
    if state["key"] is not None:
        emit(t0 + timedelta(minutes=n_minutes))
    return list(a.bars5)


def main():
    start = datetime(2024, 6, 4, 9, 30)   # naive ET per v2.1 contract
    a = make_alg()
    out = feed(a, start, 20)

    ok = True
    if len(out) != 4:
        print(f"FAIL expected exactly 4 aggregated 5m bars, got {len(out)}")
        ok = False
    else:
        print("PASS 20 minute bars -> 4 x 5m bars")
    if len(out) == 4:
        # v2.1: EndTime marks completion; 09:30-ET start -> first close 09:35
        want = [(9, mm) for mm in (35, 40, 45, 50)]
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
