"""Local chronology tests for SCIFVG v1.0 signal logic (no LEAN dependency).

Extracts the state machine from scifvg_main.py into a pure-Python harness and
runs deterministic scenarios: sweep/reclaim, CISD reference selection, FVG
detection/inversion, pending cancellation, and mirror symmetry.
"""
import sys
import json
import types
from datetime import datetime, timedelta

sys.path.insert(0, ".")
ROOT = r"C:\\Users\\Jostb\\OneDrive\\Documents\\Hermes Projects\\Strategy"

src = open("scifvg_main.py").read()

# stub the LEAN import surface before exec
stub_src = '''
class _StubBase:
    def __init__(self, *a, **k):
        pass
    def add_chart(self, chart):
        self.charts[chart.name] = chart

    def add_series(self, chart_name, series):
        self.charts[chart_name].series[series.name] = series


class QCAlgorithm(_StubBase):
    pass


class FeeModel(_StubBase):
    pass


class OrderFee:
    def __init__(self, *a):
        pass


class CashAmount:
    def __init__(self, *a):
        pass


class _EnumNS:
    SUBMITTED = 101
    FILLED = 102
    CANCELED = 103
    CANCEL_PENDING = 104
    INVALID = 105


OrderStatus = _EnumNS
class _Pt:
    def __init__(self, x, y, label=""):
        self.x, self.y, self.label = x, y, label


class Series:
    def __init__(self, name, series_type=None):
        self.name = name
        self.series_type = series_type
        self.values = []

    def add_point(self, x, y, label=""):
        self.values.append(_Pt(x, y, label))


class _ST:
    SCATTER = 1
    LINE = 0


SeriesType = _ST


class ScatterSeries:
    def __init__(self, name):
        self.name = name
        self.values = []

    def add_point(self, x, y, label=""):
        self.values.append(_Pt(x, y, label))


class Chart:
    def __init__(self, name):
        self.name = name
        self.series = {}

    def add_series(self, s):
        self.series[s.name] = s





Futures = types.SimpleNamespace(Indices=types.SimpleNamespace(
    NASDAQ_100_E_MINI="NQ", MICRO_NASDAQ_100_E_MINI="MNQ",
    SP_500_E_MINI="ES", DOW_30_E_MINI="YM", RUSSELL_2000_E_MINI="RTY"))
Resolution = types.SimpleNamespace(MINUTE="minute")
DataMappingMode = types.SimpleNamespace(OPEN_INTEREST=0)
DataNormalizationMode = types.SimpleNamespace(RAW=0)
TimeZones = types.SimpleNamespace(UTC="utc")
'''
mod = types.ModuleType("scifvg_extract")
mod.__dict__["timedelta"] = timedelta
mod.__dict__["datetime"] = datetime
mod.__dict__["types"] = types

exec(compile(stub_src, "<stubs>", "exec"), mod.__dict__)
exec(compile(src.replace("from AlgorithmImports import *", ""), "scifvg_main.py", "exec"), mod.__dict__)

Alg = mod.SweepCisdIfvgAlgorithm
FUNNEL_KEYS = mod.FUNNEL_KEYS


def make_alg():
    a = Alg.__new__(Alg)
    a.fun = {k: 0 for k in FUNNEL_KEYS}
    a.h4_min_span_min = 210     # BUG2 wall-clock span gate (set in initialize())
    a.h4_max_offset0 = 1
    a.h4_gap_pending = False
    a.d_bars5_total = 0
    a.tzcheck_ok = 0
    a.qty_max_seen = 0
    a._flatten_tickets = []
    class _OS:
        def __init__(self):
            self.store = {}
        def save_bytes(self, k, b):
            self.store[k] = bytes(b)
    a.object_store = _OS()
    a._pending_events = []
    a._ev_candidates = []    # v2.6 E19B candidates (post-reclaim)
    a._ev_results = []
    a._tr_series = []
    a._atr5 = None
    a.charts = {}
    a._ev_charts = set()
    a.trade_economics = []
    a._starting_tpv = 100000.0
    a.trade_rs = []
    a._minq = []             # v2.6 minute-bar drain queue
    a._ledger_exp_usd = 0.0
    a._fees_modeled_total = 0.0
    a._abs_now = 0
    a.time = None
    a.exp_hash = "test"
    a._last_min_close = None

    a.unfilled_watch = []
    a.unfilled_resolved_n = 0
    a.Debug = lambda *a2, **k2: None
    a.RuntimeStatistics = {}
    a.stop_ticket = None
    a.tp_ticket = None
    a.order_purpose = {}
    a.pos_side = 0
    a.exit_qty_acc = 0
    a.entry_avg = None
    a.risk_dist = None
    a.last_mapped = None
    a.cfg = {
        "sweep_min_ticks": 4, "sweep_max_ticks": 96, "reclaim_bars": 3,
        "cisd_max_bars": 12, "inv_max_bars": 12, "retest_max_bars": 24,
        "fvg_min_ticks": 4, "fvg_max_age_bars": 60, "stop_buffer_ticks": 4,
        "target_r": 2.0, "risk_usd": 100.0, "max_contracts": 10,
        "commission_per_side": 0.50, "slippage_ticks": 1,
    }
    # v2.6 E19B knobs
    a.cfg.setdefault("event_horizons", [120])
    a.cfg.setdefault("counter_bias_arm", False)
    a.event_predicate_names = ("sweep_reclaim_v1",)
    a.tick = 0.25
    a.point_value = 2.0
    a.slippage_ticks = int(a.cfg["slippage_ticks"])
    a.ny = None
    a.bars5 = []
    a.h4_pub = []
    a.h4_bucket = None
    a.swing_hi = []
    a.swing_lo = []
    a.bias = -1          # tests default bearish (short side); flip for longs
    a.setup = None
    a.session_tried = set()
    a.cur_session = None
    a.pdh = 21000.0
    a.pdl = 20900.0
    a.cur_high = None
    a.cur_low = None
    a.order_purpose = {}
    a.pos_qty = 0
    return a


IDX = [0]


def bar(a, o, h, l, c, et=None):
    """Feed one completed 5m bar through the machine."""
    IDX[0] += 1
    if et is None:
        et = datetime(2024, 3, 4, 9, 30) + timedelta(minutes=5 * IDX[0])
    b = {"open": float(o), "high": float(h), "low": float(l), "close": float(c),
         "idx": len(a.bars5), "et": et}
    a.bars5.append(b)

    if a.cur_high is None or b["high"] > a.cur_high:
        a.cur_high = b["high"]
    if a.cur_low is None or b["low"] < a.cur_low:
        a.cur_low = b["low"]
    # inline h4 accumulate (single-bucket tests never publish)
    bid = (et.year, et.month, et.day, et.hour // 4)
    if a.h4_bucket is None or a.h4_bucket["id"] != bid:
        if a.h4_bucket is not None:
            pass  # publish skipped in unit tests
        a.h4_bucket = {"id": bid, "bars": [], "offset0": 0}
    a.h4_bucket["bars"].append(b)

    if a.setup is not None and a.setup["stage"] == "PENDING" and a.pos_qty == 0:
        a._manage_pending(b, b["idx"], et, et.date())
    if a._new_setup_allowed() and a.bias in (1, -1):
        a._try_arm_attempt(b, b["idx"], et, et.date())
    if a.setup is not None and a.setup["stage"] in ("SWEPT", "CISD", "INV"):
        if a.setup["arm_sk"] == et.date():
            a._advance_setup(b, b["idx"], et, et.date())
        else:
            a._cancel_pending(f"{a._sk(a.setup['side'])}_cancel_window")
    return b


def test_short_sweep_reclaim_cisd():
    a = make_alg()
    # drift up into PDH with a bullish candle (mirrored CISD reference),
    # then sweep above PDH and close back below
    bar(a, 20985, 21006, 20983, 21004)          # bullish push ABOVE PDH
    # (arms attempt: high 21006 > PDH 21000); next bar closes back below:
    b = bar(a, 21004, 21005, 20990, 20992)
    assert a.setup is not None or True
    assert a.setup is not None and a.setup["stage"] == "CISD", a.setup
    assert a.setup["extreme"] >= 21002.0
    assert a.fun["S_attempts"] == 1 and a.fun["S_sweep_ok"] == 1
    print("PASS short sweep->reclaim; extreme:", a.setup["extreme"],
          "ref_open:", a.setup["ref_open"])
    return a


def test_no_reclaim_times_out():
    a = make_alg()
    bar(a, 21010, 21012, 21005, 21008)
    b1 = bar(a, 21008, 21006, 21002, 21004)   # sweep attempt arms? no: pen<min
    # force sweep with deep penetration but no reclaim for reclaim_bars bars
    a2 = make_alg()
    bar(a2, 21010, 21012, 21005, 21008)
    bar(a2, 21008, 21004 + 2 + 1, 20999, 21003)   # sweeps, stays above? close 21003 > PDH -> no reclaim yet
    # wait: close must be BELOW pdh for reclaim; keep it below
    print("note: reclaim semantics checked via dedicated scenario")
    return a2


def test_long_mirror():
    a = make_alg()
    a.bias = 1
    a.pdh, a.pdl = 21000.0, 20900.0
    bar(a, 20890, 20895, 20888, 20892)
    # long sweep: low below PDL by 8 ticks, closes back above
    bar(a, 20892, 20893, 20900 - 2 - 0.01, 20897)
    assert a.setup is not None, "long setup should arm"
    assert a.setup["stage"] in ("CISD", "SWEPT")
    print("PASS long mirror armed; stage:", a.setup["stage"],
          "funnel L_attempts:", a.fun["L_attempts"])
    return a


def test_fvg_scan_and_dead():
    a = make_alg()
    # bearish FVG: fast DROP leaves High[i] below Low[i-2]
    a.bars5.append({"open": 101, "high": 102, "low": 101.5, "close": 101, "idx": 0, "et": None})
    a.bars5.append({"open": 100, "high": 101, "low": 99, "close": 99.5, "idx": 1, "et": None})
    a.bars5.append({"open": 99.5, "high": 100, "low": 98, "close": 98.8, "idx": 2, "et": None})
    gaps = a._scan_fvgs(2, 1)
    assert len(gaps) == 1 and abs(gaps[0]["hi"] - 101.5) < 1e-9 and abs(gaps[0]["lo"] - 100.0) < 1e-9, gaps
    assert not a._dead(gaps[0], 2, 1)
    # now close below gap lo -> dead
    a.bars5.append({"open": 98.8, "high": 99.4, "low": 97, "close": 97.5, "idx": 3, "et": None})
    assert a._dead(gaps[0], 3, 1)
    print("PASS fvg scan/dead")


def test_sizing():
    a = make_alg()
    dist = 25.0
    qty = int(float(a.cfg["risk_usd"]) / (dist * a.point_value))
    assert qty == 2, qty
    dist = 300.0
    qty = int(100.0 / (dist * 2.0))
    assert qty == 0, "should skip when 1 micro exceeds risk"
    print("PASS sizing math")


def feed_h4_buckets(a, levels):
    """Feed one fully-spanning 4H bucket per level (~4h wall-clock each)."""
    from datetime import datetime as dt
    base = dt(2024, 1, 1)
    for k, px in enumerate(levels):
        et0 = base + timedelta(hours=4 * k)
        bid = (et0.year, et0.month, et0.day, et0.hour // 4)
        if a.h4_bucket is not None and a.h4_bucket["id"] != bid:
            a._publish_h4(bid)
        if a.h4_bucket is None or a.h4_bucket["id"] != bid:
            a.h4_bucket = {"id": bid, "bars": [], "offset0": 0,
                           "t0": et0, "tN": et0}
        # bars every 5 minutes across the full 4h => span ~235 min
        for q in range(48):
            e = et0 + timedelta(minutes=5 * q + 1)
            a.h4_bucket["bars"].append({"open": px, "high": px, "low": px,
                                        "close": px, "et": e})
            a.h4_bucket["tN"] = e
    a._publish_h4((-1, -1, -1, -99))


def test_partial_4h_bucket_discarded():
    from datetime import datetime as dt
    a = make_alg()
    feed_h4_buckets(a, [100, 99, 98, 90, 91, 92])   # establish baseline pubs
    n_before = len(a.h4_pub)
    # a PARTIAL bucket (only 30 minutes of span) must be discarded
    et = dt(2024, 1, 2)
    a.h4_bucket = {"id": (2024, 1, 2, 0), "bars": [], "offset0": 0,
                   "t0": et, "tN": et}
    for k in range(6):
        e = et + timedelta(minutes=5 * k + 1)
        a.h4_bucket["bars"].append({"open": 50, "high": 50, "low": 50,
                                    "close": 50, "et": e})
        a.h4_bucket["tN"] = e
    a._publish_h4((2024, 1, 2, 9))
    assert len(a.h4_pub) == n_before, "partial-span bucket must NOT publish"
    assert a.h4_gap_pending is True, "gap flag must invalidate next confirmation"
    print("PASS partial 4H bucket discarded + gap invalidation")

def test_bias_symmetry():
    a = make_alg()
    # bearish BOS: close below confirmed swing low
    feed_h4_buckets(a, [100, 99, 98, 90, 91, 92, 91, 89])
    assert a.bias == -1, f"expected bear after bear BOS, got {a.bias}"
    assert a.swing_lo and a.swing_lo[-1] == (3, 90.0), a.swing_lo
    # recovery without flip yet (no confirmed swing high above the recovery)
    feed_h4_buckets(a, [90, 91, 92, 97, 92, 91, 92, 93])
    assert a.bias == -1, "should remain bearish before bull BOS"
    # bullish BOS: close above confirmed swing high at idx 11 -> MUST flip bull
    feed_h4_buckets(a, [95, 96, 97, 98, 99, 100, 101, 102])
    assert any(s == (11, 97.0) for s in a.swing_hi), a.swing_hi
    assert a.bias == 1, f"REGRESSION: bias did not flip bullish, got {a.bias}"
    print("PASS bias symmetry (bear -> bull flip works)")


def test_fvg_orientation_symmetry():
    a = make_alg()
    # bearish FVG series (for LONG setups): drop leaves High[i] < Low[i-2]
    a.bars5.append({"open": 101, "high": 102, "low": 101.5, "close": 101, "idx": 0, "et": None})
    a.bars5.append({"open": 100, "high": 101, "low": 99, "close": 99.5, "idx": 1, "et": None})
    a.bars5.append({"open": 99.5, "high": 100, "low": 98, "close": 98.8, "idx": 2, "et": None})
    long_gaps = a._scan_fvgs(2, 1)
    short_gaps = a._scan_fvgs(2, -1)
    assert len(long_gaps) == 1 and abs(long_gaps[0]["lo"] - 100.0) < 1e-9
    assert len(short_gaps) == 0, "bearish move must not create bullish gaps"
    # bullish FVG series (for SHORT setups): rally leaves Low[i] > High[i-2]
    a.bars5.append({"open": 98, "high": 98.2, "low": 97, "close": 98, "idx": 3, "et": None})
    a.bars5.append({"open": 99, "high": 101, "low": 98.8, "close": 100.5, "idx": 4, "et": None})
    a.bars5.append({"open": 101, "high": 102, "low": 101.4, "close": 101.8, "idx": 5, "et": None})
    short_gaps = a._scan_fvgs(5, -1)
    assert any(g["created"] == 5 for g in short_gaps), short_gaps
    g = [x for x in short_gaps if x["created"] == 5][0]
    assert abs(g["lo"] - 98.2) < 1e-9 and abs(g["hi"] - 101.4) < 1e-9, g
    # dead-check mirror: close ABOVE gap top kills a bullish (short-side) gap
    assert not a._dead(g, 5, -1)
    a.bars5.append({"open": 102, "high": 103, "low": 101.9, "close": 102.8, "idx": 6, "et": None})
    assert a._dead(g, 6, -1)
    print("PASS fvg orientation symmetry")


def test_4h_starttime_bucketing():
    """Commit-coupled guard: with END-time keys offset0 was 295-300 and every
    real bucket was rejected; with START-time keys offset0<=1 must hold."""
    from datetime import datetime as dt
    a = make_alg()
    # one full bucket: bars ending 18:05 .. 22:00 ET-equivalent (naive here)
    base = dt(2024, 6, 4, 20, 5)   # bucket [20,24): first bar ends 20:05
    bid = (base.year, base.month, base.day, base.hour // 4)
    a.h4_bucket = {"id": bid, "bars": [], "offset0": None, "t0": None, "tN": None}
    st0 = base - timedelta(minutes=5)
    a.h4_bucket["offset0"] = (st0.hour % 4) * 60 + st0.minute   # = 0
    for q in range(48):
        e = base + timedelta(minutes=5 * q)
        a.h4_bucket["bars"].append({"open": 100, "high": 100.5, "low": 99.5,
                                    "close": 100.2, "et": e})
        a.h4_bucket["tN"] = e
    a.h4_bucket["t0"] = st0
    n0 = len(a.h4_pub)
    a._publish_h4((2024, 6, 5, 1))
    assert len(a.h4_pub) == n0 + 1, "full start-aligned bucket MUST publish"
    print("PASS 4H start-time bucketing publishes full buckets")



def test_consolidator_handler_slot_discipline():
    """Drive _on_5m_consolidated (the real entry point) with 20 one-minute
    consolidations and require exactly 4 x 5m emissions on :05..:20."""
    a = make_alg()
    a.camp_start = datetime(2024, 3, 4).date()
    a.w_start = 9 * 60 + 30
    a.w_end = 12 * 60

    class _C:
        pass

    t0 = datetime(2024, 3, 4, 9, 31)
    emitted_before = 0
    state = {"key": None}
    for k in range(20):
        end = t0 + timedelta(minutes=k)
        st = end - timedelta(minutes=1)
        key = (st.year, st.month, st.day, st.hour, st.minute // 5)
        if state["key"] is not None and key != state["key"]:
            pass  # previous bucket already flushed by handler call below
        cb = _C()
        cb.open, cb.high, cb.low, cb.close = 100.0 + k * 0.01, 101.0, 99.0, 100.5
        # LEAN fires the handler only at bucket completion: emulate by calling
        # it every 5th minute with the bucket's end time.
        if (end.minute % 5) == 0:
            cb.end_time = end
            before = len(a.bars5)
            a._on_5m_consolidated(cb)
            assert len(a.bars5) == before + 1, \
                f"handler must emit exactly one bar per completed slot ({end})"
    total = len(a.bars5)
    assert total == 4, f"expected 4 consolidated bars, got {total}"
    mins = [(b["et"].hour, b["et"].minute) for b in a.bars5]
    assert mins == [(9, 35), (9, 40), (9, 45), (9, 50)], mins
    print("PASS consolidator handler emits exactly one bar per 5m slot "
          "(on_data cannot fragment)")



def test_oco_single_exit_invariant():
    """v2.4 atomic simulator: entry cycle resolves against minute bars,
    exactly ONE exit row, stop-first on same-bar ambiguity, MFE/MAE tracked."""
    a = make_alg()
    a.camp_start = datetime(2024, 3, 4).date()
    a.Debug = lambda *x, **k: None
    a.time = datetime(2024, 3, 4, 10, 15)
    a.pos_side = 1
    a.pos_qty = 1
    a.entry_avg = 18000.0
    a.risk_dist = 20.0          # stop 17980 / tp 18040 (2R)
    a.stop_px = 17980.0
    a.tp_px = 18040.0
    a.exit_qty_acc = 1
    a._eq_at_entry = 100000.0
    a._row_written = False
    a._cycle_seq = 1
    a._cyc_mfe = 0.0
    a._cyc_mae = 0.0
    a.trade_economics = []
    a.trade_rs = []
    a.exp_hash = "test"
    a.setup = {"side": 1}

    # minute 1: rises to +1.5R (MFE), dips -0.5R (MAE), no exit
    a._resolve_cycle_minute(18000, 18030, 17990, 18025,
                            datetime(2024, 3, 4, 10, 16))
    assert len(a.trade_economics) == 0, "no exit yet"
    assert abs(a._cyc_mfe - 30.0) < 1e-9 and abs(a._cyc_mae + 10.0) < 1e-9

    # minute 2: touches BOTH tp and stop inside one bar -> pessimistic STOP
    a._resolve_cycle_minute(18000, 18045, 17975, 18000,
                            datetime(2024, 3, 4, 10, 17))
    assert len(a.trade_economics) == 1, "exactly one exit"
    row = a.trade_economics[0]
    assert row["exit_kind"] == "stop" and row["r_gross"] == -1.0
    # v2.6: net r must be strictly below gross (friction), never above
    assert -1.05 < row["r"] < -1.0, f"net r {row['r']} vs gross {row['r_gross']}"
    assert row["friction_r"] < 0 and abs(row["friction_r"]) < 0.05
    # v2.6 identity accumulators must have moved by exactly this row's USD
    pv_qty = a.point_value * max(int(a.pos_qty) or 1, 1)
    exp_row_usd = row["r_gross"] * row["risk_dist"] * pv_qty \
        + row["friction_r"] * row["risk_dist"] * pv_qty
    assert abs((a._ledger_exp_usd - exp_row_usd)) < 1e-6
    assert row["cycle_id"] and row["candidate"] == "candidate"
    assert row["mfe_r"] == 2.25 and row["mae_r"] == -1.25  # m2 high 18045
    assert a.pos_side == 0 and a.pos_qty == 0 and a.entry_avg is None

    # further minutes after flat: resolver is inert
    a._resolve_cycle_minute(18000, 18100, 17950, 18050,
                            datetime(2024, 3, 4, 10, 18))
    assert len(a.trade_economics) == 1, "no phantom exits after flat"

    print("PASS atomic bracket: one clean exit per cycle, stop-first "
          "pessimism, MFE/MAE captured")


def test_protocol_conformance():
    """G5: assert the versioned deviations (PROTOCOL_CONFORMANCE.md v2.3)
    are actually implemented - silent drift fails here."""
    src = open(ROOT + r"\scifvg_main.py", encoding="utf-8").read()
    # C1: every order submission uses mapped symbol
    assert "sym = self.fut.mapped" in src
    assert "self.limit_order(self.fut.symbol" not in src \
        and "self.market_order(self.fut.symbol" not in src
    # D1: single mirrored code path for both sides
    assert "_sk(side)" in src and side_symmetry_present(src)
    # D2: nearest-to-price gap selection with age cap
    assert '"_prox"' in src and "fvg_max_age_bars" in src
    # D3: midpoint inversion rule present; through-filter gone
    assert "mid" in src and "/ 2.0" in src
    # D4: contiguous pivot confirmation
    assert "h4_gap_pending" in src
    # D5: EOD + rollover fail-closed
    assert 'tag=f"EOD-FLATTEN-' in src and "ROLLOVER-FLATTEN" in src
    # D7: attempt counters per side
    assert "_attempts" in src
    # OCO void-leg invariant
    assert "oco_void_legs" in src
    print("PASS protocol conformance: versioned deviations all present")


def side_symmetry_present(src):
    """Long/short share one parameterized path (no duplicated logic)."""
    return src.count("def _try_arm_attempt") == 1 \
        and src.count("def _advance_setup") == 1



def test_deterministic_replay():
    """G3: same inputs twice -> identical funnel + ledger (hash equal)."""
    import hashlib

    def run_once():
        a = make_alg()
        a.camp_start = datetime(2024, 3, 4).date()
        a.w_start = 9 * 60 + 30
        a.w_end = 12 * 60
        # deterministic scenario: sweep down then CISD up (short cycle)
        bar(a, 21000.0, 21005.0, 20995.0, 20998.0)
        bar(a, 20998.0, 21000.0, 20890.0, 20895.0)   # sweep below PDL 20900
        for k in range(5):
            bar(a, 20895.0 + k, 20900.0 + k, 20894.0 + k, 20899.0 + k)
        state = json.dumps({
            "funnel": a.fun, "bars": len(a.bars5),
            "setup_stage": a.setup["stage"] if a.setup else None,
        }, sort_keys=True)
        return hashlib.md5(state.encode()).hexdigest()

    h1 = run_once()
    h2 = run_once()
    assert h1 == h2, f"replay diverged: {h1} != {h2}"
    print("PASS deterministic replay (G3): identical ledgers on repeat")



def test_mirrored_cisd_reference():
    """D1: longs reference last bearish candle; shorts last bullish candle."""
    a = make_alg()
    a.camp_start = datetime(2024, 3, 4).date()
    a.Debug = lambda *x, **k: None
    # bullish push above PDH (arms attempt), then close back below (reclaim)
    bar(a, 20985.0, 21006.0, 20983.0, 21004.0)
    bar(a, 21004.0, 21005.0, 20990.0, 20992.0)
    s = a.setup
    assert s is not None and s["side"] == -1, f"short setup expected: {a.fun}"
    assert s["stage"] == "CISD", s["stage"]
    # reference must be a BULLISH candle (close>open), not bearish
    ref_idx = s.get("ref_idx")
    if ref_idx is not None:
        bb = a.bars5[ref_idx]
        assert bb["close"] > bb["open"], \
            f"short CISD ref must be bullish candle: {bb}"
    print("PASS mirrored CISD: short setup references bullish counter-candle")


def _mk_open_cycle(a):
    """Fixture: open in-flight long cycle, entry 18000 / stop 17990 / tp 18020."""
    a.pos_side = 1
    a.pos_qty = 1
    a.entry_avg = 18000.0
    a.stop_px = 17990.0
    a.tp_px = 18020.0
    a.risk_dist = 10.0
    a._cyc_mfe = 0.0
    a._cyc_mae = 0.0
    a._cyc_entry_ts = "2024-03-04 10:00:00"
    a._row_written = False
    a._cycle_seq = 1
    a.exp_hash = "t26"
    a.trade_economics = []
    a.trade_rs = []
    return a


def test_identity_gates_can_go_red():
    """v2.6 NEGATIVE tests: every corrected identity must FAIL when its
    invariant is violated — proving none of the gates is vacuous
    (the E18S defect was gates that could not go red)."""
    import types as _t

    def mk_rec(ledger_exp, builder_pl, fees_actual, fees_modeled,
               rows=None, anomalies=0):
        a = make_alg()
        a._ledger_exp_usd = ledger_exp
        a._fees_modeled_total = fees_modeled
        a.trade_builder = _t.SimpleNamespace(closed_trades=[
            _t.SimpleNamespace(profit_loss=builder_pl,
                               total_fees=fees_actual)])
        a.portfolio = _t.SimpleNamespace(total_portfolio_value=100000.0)
        # cash view kept clean: TPV moved exactly by builder P&L minus fees
        a._starting_tpv = 100000.0 - (builder_pl - fees_actual)
        if rows is None:
            rows = [{"exit_kind": "stop", "r": -1.05, "r_gross": -1.0,
                     "risk_dist": 10.0}]
        a.trade_economics = rows
        a.fun.update({"L_fills": len(rows), "S_fills": 0,
                      "L_cycles_opened": len(rows), "S_cycles_opened": 0,
                      "atomic_exits": len(rows),
                      "anomalous_exit_events": anomalies,
                      "untracked_fills": 0})
        a.cfg["target_r"] = 2.0
        return a._reconcile_pnl()

    # consistent world -> GREEN (net r = (-1.0*10*2 - 1) / 20 = -1.05)
    base = mk_rec(-21.0, -21.0, 1.0, 1.0)
    assert base["ok"], f"consistent world must reconcile: {base}"
    assert base["i1_ledger_resid"] <= 25 and base["i2_resid"] <= 25

    # Identity 1 RED: ledger expectation diverges from broker bookings
    # (the frictionless-booking failure mode; drift scaled past tolerance)
    r1 = mk_rec(-121.0, -21.0, 1.0, 1.0)
    assert not r1["ok"] and r1["i1_ledger_resid"] > 25, r1

    # Identity 2 RED: modeled total fees diverge from actual total fees
    r2 = mk_rec(-21.0, -21.0, 101.0, 1.0)
    assert not r2["ok"] and r2["i2_resid"] > 25, r2

    # Identity 3 RED (anomaly prong): unexplained exit event breaks I3
    r3 = mk_rec(-21.0, -21.0, 1.0, 1.0, anomalies=1)
    assert not r3["ok"], r3

    # Barrier-purity RED: stop row whose gross R drifted off -1.0 by
    # construction cannot pass (frictionless misbooking detector)
    bad_rows = [{"exit_kind": "stop", "r": -1.05, "r_gross": -0.97,
                 "risk_dist": 10.0}]
    r4 = mk_rec(-21.0, -21.0, 1.0, 1.0, rows=bad_rows)
    assert not r4["ok"] and r4["barrier_purity_violations"] >= 1, r4

    print("PASS identity negative tests: I1/I2/I3/purity all go red "
          "on violation")


def test_exit_time_algo_clock_and_drain():
    """v2.6 regressions: (a) exit_time stamped from algo clock (exchange-
    local), never the UTC bar.end_time that shifted E18S ledgers 4-5h;
    (b) multi-bar batches drain fully — a missed minute event can no longer
    starve the stop until EOD (shadowMOC avgL=-1.287 failure mode)."""
    from datetime import datetime as _dt
    a = make_alg()
    _mk_open_cycle(a)
    # two queued minute bars: first benign, second breaches stop 17990
    a._minq = [{"o": 18000, "h": 18001, "l": 17995, "c": 17996},
               {"o": 17996, "h": 17997, "l": 17980, "c": 17985}]
    a.time = _dt(2024, 3, 4, 10, 17)
    a._drain_minq()
    assert len(a.trade_economics) == 1, "second bar must resolve"
    row = a.trade_economics[0]
    assert row["exit_kind"] == "stop"
    et = _dt.fromisoformat(row["exit_time"])
    assert (et.hour, et.minute) == (10, 17), \
        f"exit_time not algo-clock ET: {row['exit_time']}"
    assert a._minq == [], "queue must be empty after resolution"
    print("PASS algo-clock exit stamps + full-batch drain (starvation fixed)")


def test_e19b_candidates_post_reclaim():
    """E19B v2.7: ONE candidate per reclaim-confirmed sweep; counter arm is a
    result sub-key (side-opposed R of identical geometry), never a mirrored
    twin. bias_aligned tag isolates the HTF gate; horizons resolve on
    wall-clock minutes; ledgers land in Object Store."""
    a = make_alg()
    a.camp_start = datetime(2024, 3, 4).date()
    a.Debug = lambda *x, **k: None
    a.cfg["variant"] = "events_only"
    a.cfg["event_horizons"] = [30, 60, 120]
    bar(a, 20985.0, 21006.0, 20983.0, 21004.0)   # penetrates PDH (attempt)
    assert len(a._ev_candidates) == 0, \
        "E19 defect: capture happened at ATTEMPT, before depth/reclaim"
    assert a.setup is not None and a.setup.get("bias_aligned") is not None, \
        "arming must tag bias_alignment"
    bar(a, 21004.0, 21005.0, 20990.0, 20992.0)   # closes back below -> reclaim
    assert len(a._ev_candidates) == 1, \
        f"ONE candidate per reclaim expected, got {len(a._ev_candidates)}"
    c0 = a._ev_candidates[0]
    assert c0["side"] == -1 and "event_id" in c0 and "bias_aligned" in c0
    assert {"shadow_cisd", "shadow_fvg", "shadow_ifvg"} <= set(c0)
    # advance via wall clock: 120 minutes after reclaim resolves h=120 only.
    import types as _types
    px0 = c0["px"]
    p_ = 20992.0
    base = datetime(2024, 3, 4, 10, 0)
    from datetime import timedelta as _td

    def _adv(minutes, price):
        et2 = base + _td(minutes=minutes)
        agg = {"high": price + 1.5, "low": price - 0.5, "close": price,
               "et": et2}
        a._abs_now += 1
        a._advance_events(agg)

    pr_ = px0
    for m in range(5, 125, 5):
        pr_ -= 0.5
        _adv(m, pr_)
    res = [e for e in a._ev_results if e["event_id"] == c0["event_id"]]
    hs = sorted(e["h_min"] for e in res)
    assert hs == [30, 60, 120], f"wall-clock horizons resolved {hs}"
    r120 = next(e for e in res if e["h_min"] == 120)
    expect = ((r120["entry_px"] and (pr_) - r120["entry_px"])
              / c0["risk_dist"]) * c0["side"]
    assert abs(r120["ret_r"] - expect) < 1e-4, "R-unit math mismatch"
    assert "mfe_r" in r120 and "mae_r" in r120
    assert r120["arm"] in ("primary", "counter")
    # Chart-channel ledger export fires at end-of-algorithm:
    # ret/rd/mfe/mae/mask series per horizon, aligned+opposed.
    try:
        a.on_end_of_algorithm()
    except Exception:
        pass
    assert a.charts, "chart channel must carry event rows"
    total_pts = sum(len(sr.values)
                    for ch in a.charts.values()
                    for sr in ch.series.values())
    assert total_pts >= len(a._ev_results), \
        f"chart points {total_pts} < events {len(a._ev_results)}"
    for ch in a.charts.values():
        for sname in ch.series:
            assert sname.split("-")[-1] in ("a", "o", "rd", "mfe",
                                            "mae", "mask"), sname
    print("PASS E19B: single candidate per reclaim, event_id+bias tag, "
          "wall-clock horizons, shadow labels, ObjectStore export")


def test_ft_export_is_one_exact_32bit_series():
    """FT repair: sixteen cells use exactly two bits each in one series.

    This drives the real chart-export entry point. The four-code fixture
    repeats undecided/target/stop/ambiguous so every encoding is exercised.
    """
    a = make_alg()
    codes = (0, 1, 2, 3) * 4
    ft = {}
    for (key, target, stop), code in zip(mod.FT_CELLS, codes):
        if code == 1:
            ft[key] = target
        elif code == 2:
            ft[key] = -stop
        elif code == 3:
            ft[key] = 99
    a._ev_results = [{
        "event_id": "ft-1", "last_reclaim_et": "2024-03-04 10:00:00",
        "bias_aligned": True, "arm": "primary", "side": 1,
        "date": "2024-03-04", "h_min": 120, "ret_r": 0.0,
        "entry_px": 100.0, "stop_px": 99.0, "risk_dist": 1.0,
        "shadow_mask": 0, "shadow_cisd": False, "shadow_fvg": False,
        "shadow_ifvg": False, "ft": ft, "mfe_r": 2.0, "mae_r": -2.0,
    }]

    a._export_charts()

    assert "E19B-FT" in a.charts, a.charts.keys()
    chart = a.charts["E19B-FT"]
    assert set(chart.series) == {"a"}, chart.series.keys()
    assert len(chart.series["a"].values) == 1
    packed = chart.series["a"].values[0].y
    expected = sum(code << (2 * i) for i, code in enumerate(codes))
    assert packed == float(expected)
    assert 0 <= expected <= (2 ** 32 - 1)
    assert int(float(expected)) == expected, "32-bit payload must be exact in float64"
    assert a._n_ft_rows == 1
    print("PASS FT export: one exact 32-bit/two-bit-per-cell series")


def test_ft_export_preserves_event_time_and_uniquifies_collisions():
    """FT x carries result time; same-time events get reversible offsets."""
    a = make_alg()
    event = {
        "event_id": "ft-1", "last_reclaim_et": "2024-03-04 10:00:00",
        "bias_aligned": True, "arm": "primary", "side": 1,
        "date": "2024-03-04", "h_min": 120, "ret_r": 0.0,
        "entry_px": 100.0, "stop_px": 99.0, "risk_dist": 1.0,
        "shadow_mask": 0, "shadow_cisd": False, "shadow_fvg": False,
        "shadow_ifvg": False, "ft": {}, "mfe_r": 0.0, "mae_r": 0.0,
    }
    a._ev_results = [dict(event), dict(event, event_id="ft-2")]
    a._export_charts()
    points = a.charts["E19B-FT"].series["a"].values
    expected = datetime(2024, 3, 4, 10, 0)
    assert [point.x for point in points] == [
        expected, expected + timedelta(seconds=1)]
    print("PASS FT export: event time preserved with collision ordinal")


def test_ft_chart_added_after_points_for_snapshot_semantics():
    """Hosted AddChart snapshots the populated object at registration."""
    a = make_alg()
    base = {
        "event_id": "ft-1", "last_reclaim_et": "2024-03-04 10:00:00",
        "bias_aligned": True, "ret_r": 0.0, "risk_dist": 1.0,
        "shadow_cisd": False, "shadow_fvg": False, "shadow_ifvg": False,
        "ft": {"T0.5S0.5": 0.5}, "mfe_r": 0.5, "mae_r": 0.0,
    }
    a._ev_results = [dict(base, h_min=120)]
    snapshots = {}
    a.add_chart = lambda chart: snapshots.setdefault(
        chart.name, {name: len(series.values)
                     for name, series in chart.series.items()})
    a._export_charts()
    assert snapshots["E19B-FT"]["a"] == 1, snapshots
    print("PASS FT export: populated chart registered after point creation")


def test_ft_export_stays_within_four_custom_charts():
    """FT repair replaces the redundant H*=120 base chart, not chart five."""
    a = make_alg()
    base = {
        "event_id": "ft-1", "last_reclaim_et": "2024-03-04 10:00:00",
        "bias_aligned": True, "ret_r": 0.0, "risk_dist": 1.0,
        "shadow_cisd": False, "shadow_fvg": False, "shadow_ifvg": False,
        "ft": {}, "mfe_r": 0.0, "mae_r": 0.0,
    }
    a._ev_results = [dict(base, h_min=h) for h in (30, 60, 120, 240)]
    a._export_charts()
    assert set(a.charts) == {
        "E19B-FT", "E19B-h30", "E19B-h60", "E19B-h240"}, a.charts.keys()
    print("PASS FT export: four-chart ceiling respected")


def test_ft_series_reuses_existing_global_quota_name():
    """LEAN quotas unique series names globally, so FT must reuse `a`."""
    a = make_alg()
    a._ev_results = [{
        "event_id": "ft-1", "last_reclaim_et": "2024-03-04 10:00:00",
        "bias_aligned": True, "h_min": 120, "ret_r": 0.0,
        "risk_dist": 1.0, "shadow_cisd": False, "shadow_fvg": False,
        "shadow_ifvg": False, "ft": {}, "mfe_r": 0.0, "mae_r": 0.0,
    }]
    a._export_charts()
    assert set(a.charts["E19B-FT"].series) == {"a"}
    print("PASS FT export: no eleventh unique series name")


def test_ft_screen_probability_nondecreasing_in_stop_width():
    """For each fixed target, widening the stop cannot lower target-first p."""
    import d44_e19b_ft as ft_driver
    assert hasattr(ft_driver, "summarize_ft_rows")
    assert hasattr(ft_driver, "assert_stop_monotonic")
    # Three event paths. For every target, widening the stop converts the
    # second path from stop-first to target-first and never the reverse.
    rows = [
        {"codes": [2, 2, 2, 2] * 4},
        {"codes": [2, 1, 1, 1] * 4},
        {"codes": [1, 1, 1, 1] * 4},
    ]
    screen = ft_driver.summarize_ft_rows(rows)
    ft_driver.assert_stop_monotonic(screen)
    for target in (0.5, 1.0, 1.5, 2.0):
        ps = [screen[f"T{target:g}S{stop:g}"]["p_target_given_decided"]
              for stop in (0.5, 1.0, 1.5, 2.0)]
        assert ps == sorted(ps), (target, ps)
        assert ps[0] < ps[-1], "fixture must prove stop width engages"
    print("PASS FT screen: target-first probability is monotone in stop width")


def test_ft_screen_prices_same_bar_ambiguity_as_stop():
    """Economic summaries retain code 3 but price it stop-first."""
    import d44_e19b_ft as ft_driver
    rows = [{"codes": [code] * 16} for code in (0, 1, 2, 3)]
    cell = ft_driver.summarize_ft_rows(rows)["T1S0.5"]
    assert cell["ambiguous"] == 1
    assert cell["n_decided"] == 3
    assert cell["p_target_given_decided"] == 1 / 3
    assert cell["mean_R_per_unit_risked"] == 0.0
    print("PASS FT screen: same-bar ambiguity is pessimistic stop-first")


def test_ft_screen_reports_maximally_optimistic_ambiguity_bound():
    """Code 3 must also expose the all-target upper bound, not hide it."""
    import d44_e19b_ft as ft_driver
    rows = [{"codes": [code] * 16} for code in (1, 2, 3)]
    cell = ft_driver.summarize_ft_rows(rows)["T1S0.5"]
    assert cell["mean_R_per_unit_risked_pessimistic"] == 0.0
    assert cell["mean_R_per_unit_risked_optimistic"] == 1.0
    assert cell["p_target_given_decided_pessimistic"] == 1 / 3
    assert cell["p_target_given_decided_optimistic"] == 2 / 3
    print("PASS FT screen: ambiguity economics bracketed stop-first..target-first")


def test_ft_screen_reports_driftless_barrier_benchmark():
    """No-overshoot fair-game target probability is S/(T+S)."""
    import d44_e19b_ft as ft_driver
    rows = [{"codes": [code] * 16} for code in (1, 2, 3)]
    cell = ft_driver.summarize_ft_rows(rows)["T1S0.5"]
    assert cell["martingale_target_probability"] == 1 / 3
    assert cell["binomial_z_pessimistic_vs_martingale"] == 0.0
    assert cell["binomial_z_optimistic_vs_martingale"] > 0
    print("PASS FT screen: driftless no-overshoot barrier benchmark reported")


def test_ft32e_committed_bounds_and_martingale_summary():
    """Committed FT32E rows must reproduce both bounds and benchmark summary."""
    import d44_e19b_ft as ft_driver
    rows = []
    for inst in ("NQ", "ES", "YM", "RTY"):
        with open(f"e19br_ft_ledger/{inst}_ft.jsonl") as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    payload = ft_driver.build_screen_payload([], rows)
    bounds = payload["ambiguity_bounds"]
    assert bounds["best_pessimistic"]["cell"] == "T2S0.5"
    assert abs(bounds["best_pessimistic"]["mean_R_per_unit_risked"]
               - 0.06481481481481481) < 1e-12
    assert bounds["best_optimistic"]["cell"] == "T1S0.5"
    assert abs(bounds["best_optimistic"]["mean_R_per_unit_risked"]
               - 0.1967654986522911) < 1e-12
    assert bounds["population"] == "decided paths only; undecided paths excluded"
    assert bounds["is_complete_horizon_upper_bound"] is False
    mart = payload["martingale_benchmark"]
    assert abs(mart["mean_abs_binomial_z"] - 1.9172729644540323) < 1e-12
    assert mart["n_cells_abs_z_gt_1_96"] == 6
    assert mart["n_cells_abs_z_le_1_96"] == 10
    assert mart["cells_abs_z_gt_1_96"] == [
        "T0.5S0.5", "T0.5S1", "T0.5S1.5", "T0.5S2", "T1S1", "T1S1.5"]
    assert mart["holm_rejections_16_cells"] == [
        "T0.5S0.5", "T0.5S1", "T0.5S1.5"]
    assert mart["n_T_ge_1_cells"] == 12
    assert mart["holm_rejections_T_ge_1_cells"] == []
    assert mart["ambiguity_robust_raw_rejections"] == []
    assert mart["proves_conditional_process_is_martingale"] is False
    print("PASS FT32E: committed ambiguity bounds + martingale summary exact")


def test_ft_ledger_required_and_count_reconciled():
    """Any non-empty event study must retrieve a non-empty, exact FT ledger."""
    import d44_e19b_ft as ft_driver
    assert hasattr(ft_driver, "validate_ft_ledger")
    for rt, rows in (({"d_ev_results": "8", "n_ft_rows": "0"}, []),
                     ({"d_ev_results": "8", "n_ft_rows": "2"},
                      [{"codes": [1] * 16}])):
        try:
            ft_driver.validate_ft_ledger(rt, rows)
        except AssertionError:
            pass
        else:
            raise AssertionError("invalid FT ledger must fail closed")
    ft_driver.validate_ft_ledger(
        {"d_ev_results": "8", "n_ft_rows": "2"},
        [{"codes": [1] * 16}, {"codes": [2] * 16}])
    print("PASS FT ledger: non-empty + exact RuntimeStatistic reconciliation")


def test_ft_ledger_rejects_vacuous_zero_event_export():
    import d44_e19b_ft as ft_driver
    for runtime in ({"d_ev_results": "0", "n_ft_rows": "0"},
                    {"n_ft_rows": "0"}):
        try:
            ft_driver.validate_ft_ledger(runtime, [])
            raise AssertionError("vacuous FT export was accepted")
        except AssertionError as exc:
            assert str(exc) != "vacuous FT export was accepted"
    print("PASS FT ledger: vacuous zero/missing event counts rejected")


def test_ft_monotonicity_rejects_vacuous_cells():
    import d44_e19b_ft as ft_driver
    empty = {key: {"p_target_given_decided": None}
             for key, _, _ in ft_driver.CELLS}
    try:
        ft_driver.assert_stop_monotonic(empty)
        raise AssertionError("all-undecided FT screen was accepted")
    except AssertionError as exc:
        assert str(exc) != "all-undecided FT screen was accepted"
    print("PASS FT screen: vacuous all-undecided cells rejected")


def test_ft_chart_read_polls_and_requests_declared_count():
    import d44_e19b_ft as ft_driver
    calls = []
    responses = [
        {"success": True, "status": "loading"},
        {"success": True, "chart": {"series": {"a": {"values": [
            {"x": 100, "y": 1.0}, {"x": 101, "y": 2.0}]}}}},
    ]
    old_read, old_time = ft_driver.chart_read, getattr(ft_driver, "time", None)
    try:
        def fake_read(pid, bid, name, **kwargs):
            calls.append((pid, bid, name, kwargs))
            return responses.pop(0)
        ft_driver.chart_read = fake_read
        class FakeTime:
            sleep = staticmethod(lambda _: None)
        ft_driver.time = FakeTime
        try:
            rows = ft_driver.ft_rows_from_chart("NQ", "bid", 2)
        except TypeError:
            rows = None
    finally:
        ft_driver.chart_read = old_read
        if old_time is None:
            del ft_driver.time
        else:
            ft_driver.time = old_time
    assert rows is not None and len(rows) == 2
    assert len(calls) == 2
    assert calls[-1][3] == {"count": 2, "start": 0,
                            "end": 2147483647}
    print("PASS FT pull: loading polled + declared count requested")


def test_sync_file_compares_exact_bytes():
    import qc_api
    old_read, old_update, old_create = (qc_api.read_files, qc_api.update_file,
                                        qc_api.create_file)
    updates = []
    try:
        qc_api.read_files = lambda _: {"main.py": "same\n"}
        qc_api.update_file = lambda pid, name, content: updates.append(content)
        qc_api.create_file = lambda *args: None
        outcome = qc_api.sync_file(1, "main.py", "same")
    finally:
        qc_api.read_files, qc_api.update_file, qc_api.create_file = (
            old_read, old_update, old_create)
    assert outcome == "updated" and updates == ["same"]
    print("PASS sync guard: trailing-byte mismatch forces update")


def test_ft_driver_main_uses_created_backtest_id():
    """Drive the real launcher path so retrieval cannot reference a stale name."""
    import d44_e19b_ft as ft_driver
    import os, tempfile
    old_cwd = os.getcwd()
    originals = {name: getattr(ft_driver, name) for name in (
        "backtest_list", "backtest_create", "poll_backtest",
        "ft_rows_from_chart")}
    seen = []
    tmp = tempfile.TemporaryDirectory()
    try:
        os.chdir(tmp.name)
        open("compile_id.txt", "w").write("compile-test")
        ft_driver.backtest_list = lambda _: []
        ft_driver.backtest_create = lambda pid, tag, params, compile_id: {
            "backtest_id": "bid-" + params["instrument"]}
        ft_driver.poll_backtest = lambda *args, **kwargs: {
            "status": "Completed.", "error": None,
            "runtimeStatistics": {"d_ev_results": "1",
                                  "n_ft_rows": "1"}}
        def fake_pull(inst, bid, expected):
            seen.append((inst, bid, expected))
            return [{"instrument": inst, "ft_row": 0, "chart_x": 1,
                     "packed_uint32": 0x55555555, "codes": [1] * 16,
                     "cells": {key: "target-first"
                               for key, _, _ in ft_driver.CELLS}}]
        ft_driver.ft_rows_from_chart = fake_pull
        ft_driver.main()
    finally:
        os.chdir(old_cwd)
        tmp.cleanup()
        for name, value in originals.items():
            setattr(ft_driver, name, value)
    assert seen == [(inst, "bid-" + inst, 1)
                    for inst in ("NQ", "ES", "YM", "RTY")]
    print("PASS FT driver: real main path retrieves created backtest IDs")


def test_event_predicate_registry_and_exact_discovery_transport():
    """Up to ten named predicates share one exact 42-bit discovery payload."""
    import event_predicates as ep
    names = ep.resolve_event_predicates(
        "sweep_reclaim_v1,bias_aligned_v1,shadow_fvg_v1")
    mask = ep.evaluate_event_predicates(names, {
        "bias_aligned": True, "shadow_cisd": False,
        "shadow_fvg": True, "shadow_ifvg": False})
    assert names == ("sweep_reclaim_v1", "bias_aligned_v1",
                     "shadow_fvg_v1")
    assert mask == 0b111
    packed = ep.pack_discovery_payload(0xDEADBEEF, mask)
    assert packed < 2 ** 53 and int(float(packed)) == packed
    assert ep.unpack_discovery_payload(float(packed)) == (0xDEADBEEF, mask)
    for bad in ("unknown_v1", "sweep_reclaim_v1,sweep_reclaim_v1"):
        try:
            ep.resolve_event_predicates(bad)
            raise AssertionError("bad predicate list accepted")
        except ValueError as exc:
            assert str(exc) != "bad predicate list accepted"
    try:
        ep.validate_discovery_predicates("discovery_only", ("shadow_fvg_v1",))
        raise AssertionError("discovery accepted without its base population")
    except ValueError as exc:
        assert str(exc) != "discovery accepted without its base population"
    try:
        ep.validate_discovery_predicates(
            "candidate", ("sweep_reclaim_v1", "shadow_fvg_v1"))
        raise AssertionError("non-default predicates accepted by trading variant")
    except ValueError as exc:
        assert str(exc) != "non-default predicates accepted by trading variant"
    try:
        ep.validate_discovery_predicates(
            "events_only", ("sweep_reclaim_v1", "shadow_fvg_v1"))
        raise AssertionError("multi-predicate legacy export accepted without mask")
    except ValueError as exc:
        assert str(exc) != "multi-predicate legacy export accepted without mask"
    ep.EVENT_PREDICATES["bad_return_v1"] = lambda _: 1
    try:
        try:
            ep.evaluate_event_predicates(("bad_return_v1",), {})
            raise AssertionError("non-boolean predicate result accepted")
        except TypeError as exc:
            assert str(exc) != "non-boolean predicate result accepted"
    finally:
        ep.EVENT_PREDICATES.pop("bad_return_v1")
    assert ep.evaluate_event_predicates(("bias_opposed_v1",), {}) == 0, \
        "missing classifier field must not create a match"
    print("PASS event predicates: registry + exact multi-family transport")


def test_default_predicate_preserves_legacy_experiment_identity():
    from scifvg_config import CONFIG_DEFAULTS, canonical_identity_config
    legacy = dict(CONFIG_DEFAULTS)
    legacy.pop("event_predicates")
    legacy.pop("random_control_seed")
    configured = dict(CONFIG_DEFAULTS)
    assert canonical_identity_config(configured) == legacy
    configured["variant"] = "discovery_only"
    assert canonical_identity_config(configured)["event_predicates"] == \
        "sweep_reclaim_v1"
    configured["event_predicates"] = "sweep_reclaim_v1,shadow_fvg_v1"
    assert canonical_identity_config(configured)["event_predicates"].endswith(
        "shadow_fvg_v1")
    random_cfg = dict(CONFIG_DEFAULTS)
    random_cfg["variant"] = "random_time_control"
    assert canonical_identity_config(random_cfg)["random_control_seed"] == \
        "RTC2-20260827-v1"
    print("PASS event predicates: legacy identity preserved; discovery identified")


def test_discovery_predicates_drive_real_reclaim_path():
    """The consolidator/setup path emits one event carrying its match mask."""
    a = make_alg()
    a.camp_start = datetime(2024, 3, 4).date()
    a.w_start, a.w_end = 9 * 60 + 30, 12 * 60
    a.cfg["variant"] = "discovery_only"
    a.cfg["event_horizons"] = [120]
    a.event_predicate_names = (
        "sweep_reclaim_v1", "bias_aligned_v1", "shadow_fvg_v1")
    a.cur_session = a._session_key(datetime(2024, 3, 4, 9, 35))
    class _C:
        pass
    for end, o, h, low, close in (
            (datetime(2024, 3, 4, 9, 35), 20985, 21006, 20983, 21004),
            (datetime(2024, 3, 4, 9, 40), 21004, 21005, 20990, 20992)):
        cb = _C()
        cb.end_time, cb.open, cb.high, cb.low, cb.close = (
            end, float(o), float(h), float(low), float(close))
        a._on_5m_consolidated(cb)
    assert len(a._ev_candidates) == 1
    event = a._ev_candidates[0]
    assert event["event_predicate_mask"] & 0b001
    assert event["event_predicate_mask"] & 0b010
    assert event["event_predicate_names"] == list(a.event_predicate_names)
    print("PASS discovery predicates: real reclaim path carries family mask")


def test_discovery_export_packs_family_mask_above_ft32():
    """One chart point carries FT32 plus ten predicate bits exactly."""
    import event_predicates as ep
    a = make_alg()
    a.cfg["variant"] = "discovery_only"
    a._ev_results = [{
        "event_id": "disc-1", "last_reclaim_et": "2024-03-04 10:00:00",
        "bias_aligned": True, "h_min": 120, "ret_r": 0.0,
        "risk_dist": 1.0, "shadow_cisd": False, "shadow_fvg": False,
        "shadow_ifvg": False, "ft": {}, "mfe_r": 0.0, "mae_r": 0.0,
        "event_predicate_mask": 0b101,
    }]
    a._export_charts()
    value = a.charts["E19B-FT"].series["a"].values[0].y
    assert ep.unpack_discovery_payload(value) == (0, 0b101)
    print("PASS discovery export: FT32 + predicate mask exact in float64")


def test_discovery_export_includes_opposed_arm_without_changing_legacy_ft32():
    """Discovery transports both arms; legacy FT32E remains aligned-only."""
    import event_predicates as ep
    opposed = {
        "event_id": "disc-opposed", "last_reclaim_et": "2024-03-04 10:00:00",
        "bias_aligned": False, "h_min": 120, "ret_r": 0.0,
        "risk_dist": 1.0, "shadow_cisd": False, "shadow_fvg": True,
        "shadow_ifvg": False, "ft": {}, "mfe_r": 0.0, "mae_r": 0.0,
        "event_predicate_mask": 0b111,
    }
    aligned = dict(opposed)
    aligned.update(event_id="disc-aligned", bias_aligned=True,
                   event_predicate_mask=0b011)
    discovery = make_alg()
    discovery.cfg["variant"] = "discovery_only"
    discovery._ev_results = [aligned, opposed]
    discovery._export_charts()
    values = discovery.charts["E19B-FT"].series["a"].values
    assert discovery._n_ft_rows == 2
    assert len(values) == 2
    expected = datetime(2024, 3, 4, 10, 0)
    assert [point.x for point in values] == [
        expected, expected + timedelta(seconds=1)]
    assert [ep.unpack_discovery_payload(point.y) for point in values] == [
        (0, 0b011), (0, 0b111)]
    legacy = make_alg()
    legacy.cfg["variant"] = "events_only"
    legacy._ev_results = [aligned, opposed]
    legacy._export_charts()
    legacy_values = legacy.charts["E19B-FT"].series["a"].values
    assert legacy._n_ft_rows == 1
    assert len(legacy_values) == 1 and legacy_values[0].x == expected
    print("PASS discovery export: both arms counted/collision-safe; legacy aligned-only")


def test_random_time_control_reservoir_matches_risk_multiset_and_horizon():
    import random_time_control as rtc
    a = types.SimpleNamespace(exp_hash="unit-random")
    specs = tuple({"source_chart_x": 1700000000 + i, "date": date,
                   "risk_dist": risk} for i, (date, risk) in enumerate((
                       ("2024-03-04", 1.0), ("2024-03-05", 2.0),
                       ("2024-03-06", 3.0))))
    rtc.initialize_random_control(a, "NQ", specs=specs, seed="unit-seed")
    for day in range(3):
        start = datetime(2024, 3, 4 + day, 9, 30)
        for i in range(55):
            et = start + timedelta(minutes=5 * i)
            close = 100.0 + 0.1 * i
            agg = {"et": et, "ts": int(et.timestamp()), "abs": i,
                   "open": close - 0.05, "high": close + 0.2,
                   "low": close - 0.2, "close": close}
            rtc.advance_random_control(
                a, agg, warm=True,
                in_window=(9 * 60 + 30 <= et.hour * 60 + et.minute < 12 * 60))
    rows = rtc.finalize_random_control(a)
    assert len(rows) == 3
    assert sorted(row["risk_dist"] for row in rows) == [1.0, 2.0, 3.0]
    assert all(row["h_min"] == 120 and len(row["ft"]) == 16 for row in rows)
    assert a._random_control["eligible"] == 90
    assert a._random_control["started"] == a._random_control["resolved"] == 3
    print("PASS random-time control: same-date plan + exact risk multiset")


def test_random_time_control_matches_source_date_and_exact_horizon_path():
    import random_time_control as rtc
    a = type("Algo", (), {})()
    a.exp_hash = "unit"
    specs = ({"source_chart_x": 1704193500, "date": "2024-01-02",
              "risk_dist": 1.25},)
    state = rtc.initialize_random_control(
        a, "NQ", specs=specs, seed="paired-unit")
    planned = state["plans"][0]
    start = datetime(2024, 1, 2, 9, 30)
    for i in range(55):
        et = start + timedelta(minutes=5 * i)
        ts = int((et - datetime(1970, 1, 1)).total_seconds())
        agg = {"et": et, "ts": ts, "close": 100 + i / 10,
               "high": 100.25 + i / 10, "low": 99.75 + i / 10}
        rtc.advance_random_control(a, agg, True,
            9 * 60 + 30 <= et.hour * 60 + et.minute < 12 * 60)
    rows = rtc.finalize_random_control(a)
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == specs[0]["date"]
    assert row["risk_dist"] == specs[0]["risk_dist"]
    assert row["random_source_index"] == 0
    assert row["random_window_index"] == planned["window_index"]
    assert row["random_path_bars"] == 24
    assert row["random_resolution_ts"] - row["random_selected_ts"] == 7200
    assert state["eligible"] == 30
    print("PASS random-time control: source-date match + exact H120 path")


def test_random_time_control_excludes_self_bar_and_rejects_path_gap():
    import random_time_control as rtc
    a = types.SimpleNamespace(exp_hash="gap")
    state = rtc.initialize_random_control(a, "NQ", specs=({
        "source_chart_x": 1700000000, "date": "2024-01-02",
        "risk_dist": 1.0},), seed="gap-seed")
    plan = state["plans"][0]
    et = datetime(2024, 1, 2, 9, 25)
    while et.hour * 60 + et.minute <= plan["minute"]:
        ts = int((et - datetime(1970, 1, 1)).total_seconds())
        extreme = et.hour * 60 + et.minute == plan["minute"]
        agg = {"et": et, "ts": ts, "close": 100.0,
               "high": 1000.0 if extreme else 100.1,
               "low": 0.0 if extreme else 99.9}
        rtc.advance_random_control(a, agg, True,
            9 * 60 + 30 <= et.hour * 60 + et.minute < 12 * 60)
        et += timedelta(minutes=5)
    candidate = state["candidates"][0]
    assert candidate["mfe_r"] == candidate["mae_r"] == 0
    assert candidate["ft"] == {} and candidate["result"] is None
    gap_et = et + timedelta(minutes=5)
    gap = {"et": gap_et,
           "ts": int((gap_et - datetime(1970, 1, 1)).total_seconds()),
           "close": 100.0, "high": 100.1, "low": 99.9}
    try:
        rtc.advance_random_control(a, gap, True, False)
        raise AssertionError("random control accepted a ten-minute path gap")
    except RuntimeError as exc:
        assert "non-contiguous" in str(exc)
    print("PASS random-time control: no self-bar lookahead; gaps fail closed")


def test_random_time_control_rejects_nonliteral_endpoint_seconds():
    import random_time_control as rtc
    a = types.SimpleNamespace(exp_hash="seconds")
    state = rtc.initialize_random_control(a, "NQ", specs=({
        "source_chart_x": 1700000000, "date": "2024-01-02",
        "risk_dist": 1.0},), seed="seconds-seed")
    plan = state["plans"][0]
    et = datetime(2024, 1, 2, plan["minute"] // 60,
                  plan["minute"] % 60, 30)
    agg = {"et": et, "ts": int((et - datetime(1970, 1, 1)).total_seconds()),
           "close": 100.0, "high": 100.1, "low": 99.9}
    try:
        rtc.advance_random_control(a, agg, True, True)
        raise AssertionError("random control accepted a second-offset endpoint")
    except RuntimeError as exc:
        assert "literal five-minute endpoint" in str(exc)
    print("PASS random-time control: second-offset endpoints fail closed")


def test_random_time_control_sampling_identity_is_et_timezone_invariant():
    import random_time_control as rtc
    def simulate(epoch_shift):
        a = type("Algo", (), {})()
        a.exp_hash = "unit"
        rtc.initialize_random_control(a, "NQ", specs=({
            "source_chart_x": 1700000000, "date": "2024-01-02",
            "risk_dist": 1.0},), seed="tz")
        start = datetime(2024, 1, 2, 9, 30)
        for i in range(55):
            et = start + timedelta(minutes=5 * i)
            ts = int((et - datetime(1970, 1, 1)).total_seconds()) + epoch_shift
            agg = {"et": et, "ts": ts, "close": 100.0 + i / 10,
                   "high": 100.25 + i / 10, "low": 99.75 + i / 10}
            rtc.advance_random_control(a, agg, True,
                9 * 60 + 30 <= et.hour * 60 + et.minute < 12 * 60)
        return [(row["event_id"], row["last_reclaim_et"], row["side"],
                 row["risk_dist"], row["ft"])
                for row in rtc.finalize_random_control(a)]
    assert simulate(0) == simulate(5 * 3600)
    print("PASS random-time control: ET identity is host-timezone invariant")


def test_random_time_control_drives_real_consolidator_without_orders():
    import random_time_control as rtc
    import d45_random_time_control as driver
    a = make_alg()
    a.camp_start = datetime(2024, 3, 4).date()
    a.camp_end = datetime(2024, 3, 4).date()
    a.w_start, a.w_end = 9 * 60 + 30, 12 * 60
    a.cfg.update({"variant": "random_time_control", "entry_mode": "signal",
                  "instrument": "NQ", "start_date": "2024-03-04",
                  "end_date": "2024-03-04", "run_segment": "dev",
                  "window_start_et": "09:30", "window_end_et": "12:00"})
    a.event_predicate_names = ()
    rtc.initialize_random_control(
        a, "NQ", specs=({"source_chart_x": 1700000000,
                          "date": "2024-03-04", "risk_dist": 1.0},),
        seed="real-path-seed")
    a.limit_order = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("random-time control placed an order"))
    a._advance_events = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("random-time control entered legacy event resolver"))
    class _C:
        pass
    start = datetime(2024, 3, 4, 9, 30)
    for i in range(55):
        cb = _C()
        cb.end_time = start + timedelta(minutes=5 * i)
        cb.close = 100.0 + 0.1 * i
        cb.open, cb.high, cb.low = cb.close - 0.05, cb.close + 0.2, cb.close - 0.2
        a._on_5m_consolidated(cb)
    a.on_end_of_algorithm()
    assert len(a._ev_results) == 1
    assert a.event_predicate_names == () and not a.order_purpose
    assert a._n_ft_rows == 1
    assert len(a.charts["E19B-FT"].series["a"].values) == 1
    decoded = rtc.unpack_random_payload(
        a.charts["E19B-FT"].series["a"].values[0].y)
    assert decoded["source_index"] == 0 and decoded["path_bars"] == 24
    assert a.RuntimeStatistics["n_ft_rows"] == "1"
    for key in driver.ZERO_RUNTIME_KEYS:
        assert key in a.RuntimeStatistics and int(a.RuntimeStatistics[key]) == 0
    print("PASS random-time control: real consolidator -> FT32, zero orders")


def test_random_time_control_spec_exactly_matches_committed_risk_distribution():
    import hashlib
    from datetime import timezone
    import random_time_control as rtc
    observed, observed_specs = {}, {}
    for instrument in ("NQ", "ES", "YM", "RTY"):
        path = f"e19br_ledgers/{instrument}_events.jsonl"
        rows = [json.loads(line) for line in open(path, encoding="utf-8")
                if line.strip()]
        observed[instrument] = [float(row["risk_dist"]) for row in rows
            if int(row["h_min"]) == 120 and row["arm"] == "primary"]
        primary = [row for row in rows
                   if int(row["h_min"]) == 120 and row["arm"] == "primary"]
        observed_specs[instrument] = [(
            int(row["ts"]),
            datetime.fromtimestamp(int(row["ts"]), timezone.utc).date().isoformat(),
            float(row["risk_dist"])) for row in primary]
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == \
            rtc.SOURCE_LEDGER_SHA256[instrument]
    assert observed == {key: list(values)
                        for key, values in rtc.RISK_DISTS.items()}
    assert observed_specs == {key: list(values)
                              for key, values in rtc.CONTROL_SPECS.items()}
    assert rtc.validate_control_spec()
    assert rtc.canonical_risk_spec_sha256() == rtc.RISK_SPEC_SHA256
    assert rtc.canonical_control_spec_sha256() == rtc.CONTROL_SPEC_SHA256
    print("PASS random-time control: committed risk distribution exact")


def test_random_control_driver_fail_closed_and_surface_identity():
    import d45_random_time_control as driver
    import random_time_control as rtc
    source_nq = [json.loads(line) for line in open(
        "e19br_ft_ledger/NQ_ft.jsonl", encoding="utf-8") if line.strip()]
    plans = rtc.build_control_plans("NQ", rtc.CONTROL_SPECS["NQ"], rtc.SEED)
    nq = []
    for index, (row, plan) in enumerate(zip(source_nq, plans)):
        nq.append(dict(row, source_index=index, side=plan["side"],
            path_bars=24, window_index=plan["window_index"],
            risk_dist=plan["risk_dist"], source_chart_x=plan["source_chart_x"],
            chart_x=driver.expected_chart_x_values(
                plan["date"], plan["window_index"])[0]))
    runtime = {
        "event_predicates": "", "d_ev_results": "388", "n_ft_rows": "388",
        "random_control_spec_version": rtc.SPEC_VERSION,
        "random_control_seed": rtc.SEED,
        "random_control_risk_sha256": rtc.RISK_SPEC_SHA256,
        "random_control_spec_sha256": rtc.CONTROL_SPEC_SHA256,
        "random_control_target": "388", "random_control_eligible": "11640",
        "random_control_started": "388", "random_control_resolved": "388",
        "random_control_invalid": "0", "random_control_order_purpose_count": "0",
        "d_cycles_opened": "0", "d_n_fillevents": "0",
        "f_L_submits": "0", "f_S_submits": "0", "f_L_fills": "0",
        "f_S_fills": "0", "f_flatten_fills": "0",
        "f_forced_flattens": "0", "eod_flattens": "0",
        "random_control_instrument": "NQ",
        "random_control_start_date": "2010-01-01",
        "random_control_end_date": "2024-12-31",
        "random_control_run_segment": "dev",
        "random_control_window": "09:30-12:00",
        "random_control_exp_hash": driver.expected_identity("NQ"),
    }
    driver.validate_random_runtime("NQ", runtime, nq)
    for key, bad in (("event_predicates", "sweep_reclaim_v1"),
                     ("random_control_invalid", "1"),
                     ("d_n_fillevents", "1"),
                     ("random_control_end_date", "2025-01-01")):
        broken = dict(runtime); broken[key] = bad
        try:
            driver.validate_random_runtime("NQ", broken, nq)
            raise AssertionError(f"random runtime accepted bad {key}")
        except AssertionError as exc:
            assert str(exc) != f"random runtime accepted bad {key}"
    nonmonotone = [dict(row, codes=list(row["codes"])) for row in nq]
    for row in nonmonotone:
        row["codes"][0], row["codes"][1] = 1, 2
    try:
        driver.validate_random_runtime("NQ", runtime, nonmonotone)
        raise AssertionError("per-market nonmonotone surface accepted")
    except AssertionError as exc:
        assert str(exc) != "per-market nonmonotone surface accepted"
    rows = []
    for instrument in ("NQ", "ES", "YM", "RTY"):
        source = [json.loads(line) for line in open(
            f"e19br_ft_ledger/{instrument}_ft.jsonl", encoding="utf-8")
            if line.strip()]
        market_plans = rtc.build_control_plans(
            instrument, rtc.CONTROL_SPECS[instrument], rtc.SEED)
        rows.extend(dict(row, source_index=index, side=plan["side"],
            path_bars=24, window_index=plan["window_index"],
            risk_dist=plan["risk_dist"], source_chart_x=plan["source_chart_x"],
            chart_x=driver.expected_chart_x_values(
                plan["date"], plan["window_index"])[0])
            for index, (row, plan) in enumerate(zip(source, market_plans)))
    sweep = json.load(open("e19br_ft_screen.json", encoding="utf-8"))
    payload = driver.build_comparison_payload([], rows, sweep)
    assert payload["surface_comparison"]["max_abs_matched_policy_delta_R"] == 0
    assert payload["surface_comparison"]["simultaneous_payoff_half_width_R"] == 0
    assert payload["surface_comparison"]["classification"] == \
        "INCONCLUSIVE_SURFACE_DIFFERENCE"
    print("PASS random control driver: gates + ambiguity-conservative comparison")


def test_random_control_driver_rejects_off_grid_and_wrong_date_chart_x():
    import d45_random_time_control as driver
    values = driver.expected_chart_x_values("2024-01-02", 0)
    assert len(values) in (1, 2)
    for value in values:
        driver.validate_selected_chart_x(value, "2024-01-02", 0)
    for bad in (min(values) + 17, min(values) + 86400):
        try:
            driver.validate_selected_chart_x(bad, "2024-01-02", 0)
            raise AssertionError("random chart validator accepted bad timestamp")
        except AssertionError as exc:
            assert str(exc) != "random chart validator accepted bad timestamp"
    print("PASS random control driver: exact date/window chart x enforced")


def test_random_control_launch_guard_allows_only_compile_id_after_compile():
    import d45_random_time_control as driver
    sync = open("d10_sync_compile.py", encoding="utf-8").read()
    assert driver.launch_status_is_allowed("")
    assert driver.launch_status_is_allowed(" M compile_id.txt\n")
    assert driver.launch_status_is_allowed(
        " M compile_id.txt\n?? compile_manifest.json\n")
    assert not driver.launch_status_is_allowed(" M scifvg_main.py\n")
    assert not driver.launch_status_is_allowed("?? unexpected.txt\n")
    assert "compile_manifest.json" in sync and '"git_head"' in sync
    assert '"source_sha256"' in sync and '"compile_id"' in sync
    print("PASS random control driver: post-compile status guard")


def test_random_control_comparison_executes_all_three_frozen_branches():
    import d45_random_time_control as driver
    zeros = [0.0] * 16
    assert driver.classify_surface(zeros, zeros, zeros, zeros, .01, .01)[0] == \
        "SURFACES_EQUIVALENT_WITHIN_PREREGISTERED_TOLERANCES"
    material_lower = [0.31] + [0.0] * 15
    assert driver.classify_surface(
        material_lower, zeros, zeros, zeros, .05, .01)[0] == \
        "EVENT_SELECTION_SURFACE_DIFFERS_MATERIALLY"
    assert driver.classify_surface(zeros, zeros, zeros, zeros, .25, .01)[0] == \
        "INCONCLUSIVE_SURFACE_DIFFERENCE"
    print("PASS random control driver: material/equivalent/inconclusive branches")


def test_discovery_modules_are_byte_verified_deployment_sources():
    """Hosted compile and OneDrive restore cover every imported source file."""
    sync = open("d10_sync_compile.py").read()
    guard = open("d43_reapply_ft.py").read()
    for name in ("scifvg_main.py", "event_predicates.py", "scifvg_config.py",
                 "random_time_control.py"):
        assert name in sync, f"sync omits {name}"
        assert name in guard, f"restore guard omits {name}"
    for marker in ("validate_discovery_predicates", "canonical_identity_config",
                   "CONTROL_SPEC_SHA256"):
        assert marker in sync, f"sync marker guard omits {marker}"
        assert marker in guard, f"restore marker guard omits {marker}"
    assert '"main.py"' in sync
    print("PASS discovery deployment: all imported sources byte-verified")


def test_sync_snapshots_one_stable_multi_file_source_set():
    source = open("d10_sync_compile.py", encoding="utf-8").read()
    assert 'if __name__ == "__main__":' in source, \
        "sync module must be import-safe before behavioral testing"
    from d10_sync_compile import stable_sources
    versions = {
        "a.py": iter(("A=1\n", "A=2\n", "A=2\n", "A=2\n")),
        "b.py": iter(("B=1\n", "B=1\n", "B=2\n", "B=2\n")),
    }
    specs = {
        "remote-a.py": ("a.py", ("A=",), (), 100),
        "remote-b.py": ("b.py", ("B=",), (), 100),
    }
    observed = stable_sources(
        specs, read_text=lambda path: next(versions[path]),
        attempts=4, sleep_s=0)
    assert observed == {"remote-a.py": "A=2\n", "remote-b.py": "B=2\n"}
    print("PASS discovery deployment: one stable multi-file source set")


def test_sync_source_reader_preserves_line_ending_bytes():
    import os
    import tempfile
    from d10_sync_compile import read_exact_text
    fd, path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(b"A=1\r\n")
        assert read_exact_text(path) == "A=1\r\n"
    finally:
        if os.path.exists(path):
            os.unlink(path)
    print("PASS sync guard: source reader preserves exact line endings")


def test_reapply_validates_complete_committed_source_set_before_restore():
    source = open("d43_reapply_ft.py", encoding="utf-8").read()
    assert 'if __name__ == "__main__":' in source, \
        "reapply module must be import-safe before behavioral testing"
    from d43_reapply_ft import committed_source_set
    specs = {
        "a.py": ((b"A=" ,), (), 100),
        "b.py": ((b"B=" ,), (), 100),
    }
    blobs = {"a.py": b"A=1\n", "b.py": b"B=2\n"}
    assert committed_source_set(
        specs, loader=lambda name: blobs[name]) == blobs
    print("PASS reapply guard: complete committed source set validated first")


def test_reapply_rolls_back_whole_bundle_on_mid_replace_failure():
    import os
    import tempfile
    from pathlib import Path
    from d43_reapply_ft import restore_source_set
    old = {"a.py": b"A='old'\n", "b.py": b"B='old'\n",
           "c.py": b"C='old'\n"}
    new = {"a.py": b"A='new'\n", "b.py": b"B='new'\n",
           "c.py": b"C='new'\n"}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name, data in old.items():
            (root / name).write_bytes(data)
        calls = {"n": 0}
        def fail_second(source, target):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("injected second replace failure")
            os.replace(source, target)
        try:
            restore_source_set(new, root=str(root), replace=fail_second)
            raise AssertionError("mid-bundle replace failure was swallowed")
        except OSError as exc:
            assert "injected second replace failure" in str(exc)
        assert {name: (root / name).read_bytes() for name in old} == old
        assert not [p for p in root.iterdir() if p.name.startswith(".")]
    print("PASS reapply guard: mid-bundle failure rolls every file back")


def test_reapply_retains_recovery_backups_when_rollback_fails():
    import os
    import tempfile
    from pathlib import Path
    import d43_reapply_ft as guard
    old = {"a.py": b"A='old'\n", "b.py": b"B='old'\n"}
    new = {"a.py": b"A='new'\n", "b.py": b"B='new'\n"}
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name, data in old.items():
            (root / name).write_bytes(data)
        real_replace = guard.os.replace
        calls = {"n": 0}
        def fail_second_forward(source, target):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("injected forward failure")
            real_replace(source, target)
        def fail_rollback(source, target):
            raise PermissionError("injected rollback failure")
        guard.os.replace = fail_rollback
        try:
            try:
                guard.restore_source_set(
                    new, root=str(root), replace=fail_second_forward)
                raise AssertionError("rollback failure was swallowed")
            except RuntimeError as exc:
                assert "backups retained" in str(exc)
        finally:
            guard.os.replace = real_replace
        backups = [p for p in root.iterdir() if "-rollback-" in p.name]
        assert backups, "rollback failure deleted every recovery backup"
        assert any(p.read_bytes() == old["a.py"] for p in backups)
        assert not [p for p in root.iterdir() if "-reapply-" in p.name]
    print("PASS reapply guard: rollback failure retains recovery backups")


def test_discovery_decoder_screens_each_matched_family():
    """One exact point is decoded once and summarized into every matched family."""
    import event_predicates as ep
    import discovery_screen as ds
    names = ("sweep_reclaim_v1", "bias_aligned_v1", "shadow_fvg_v1")
    codes = (0, 1, 2, 3) * 4
    ft32 = sum(code << (2 * i) for i, code in enumerate(codes))
    value = ep.pack_discovery_payload(ft32, 0b101)
    rows = ds.decode_discovery_points(
        "NQ", [{"x": 123, "y": float(value)}], names)
    assert rows[0]["codes"] == list(codes)
    assert rows[0]["matched_event_predicates"] == [names[0], names[2]]
    by_family = ds.summarize_discovery_rows(rows, names)
    assert by_family[names[0]]["n_ft_rows"] == 1
    assert by_family[names[1]]["n_ft_rows"] == 0
    assert by_family[names[2]]["n_ft_rows"] == 1
    runtime = {"d_ev_results": "1", "n_ft_rows": "1",
               "event_predicates": ",".join(names)}
    ds.validate_discovery_ledger(runtime, rows, names)
    for bad_runtime, bad_rows in (
            ({**runtime, "event_predicates": "sweep_reclaim_v1"}, rows),
            ({**runtime, "n_ft_rows": "2"}, rows + [dict(rows[0])])):
        try:
            ds.validate_discovery_ledger(bad_runtime, bad_rows, names)
            raise AssertionError("invalid discovery ledger accepted")
        except (AssertionError, ValueError) as exc:
            assert "invalid discovery ledger accepted" not in str(exc)
    for bad_mask in (0, 0b1000):
        bad = ep.pack_discovery_payload(ft32, bad_mask)
        try:
            ds.decode_discovery_points(
                "NQ", [{"x": 124, "y": float(bad)}], names)
            raise AssertionError(f"invalid discovery mask accepted: {bad_mask:b}")
        except ValueError as exc:
            assert "invalid discovery mask accepted" not in str(exc)
    print("PASS discovery decoder: one run screens every matched family")


def test_discovery_chart_read_polls_and_decodes_exact_declared_count():
    import discovery_screen as ds
    import event_predicates as ep
    names = ("sweep_reclaim_v1", "shadow_fvg_v1")
    packed = ep.pack_discovery_payload(1, 0b11)
    responses = [
        {"success": True, "status": "loading"},
        {"success": True, "chart": {"series": {"a": {"values": [
            {"x": 100, "y": float(packed)}]}}}},
    ]
    calls = []
    def reader(pid, bid, chart, **kwargs):
        calls.append((pid, bid, chart, kwargs))
        return responses.pop(0)
    rows = ds.discovery_rows_from_chart(
        "NQ", "bid", 1, names, read_chart=reader, sleep=lambda _: None)
    assert len(rows) == 1 and rows[0]["event_predicate_mask"] == 0b11
    assert calls[-1][3] == {"count": 1, "start": 0,
                            "end": 2147483647}
    print("PASS discovery pull: loading polled + exact count decoded")





def test_floor_params_in_read_list():
    """E19B-R: floor params must be BOTH in the raw read list AND defaults;
    a default without a raw read silently ignores cloud parameters."""
    from scifvg_config import CONFIG_KEYS, CONFIG_DEFAULTS
    for key in ("min_stop_ticks", "floor_atr_frac", "depth_min_bps",
                "depth_max_bps", "stop_buffer_bps"):
        assert key in CONFIG_KEYS, f"{key} not readable"
        assert key in CONFIG_DEFAULTS, f"{key} has no default"
    print("PASS floor params: read-list + defaults consistent")


def test_preregistration_present():
    """Structural gate: PREREGISTRATION_E19B.md must exist with the three
    outcome classes, multiplicity plan, numeric stable-positive definition,
    and exploratory labeling — committed BEFORE any E19B data pull."""
    import os
    path = ROOT + r"\PREREGISTRATION_E19B.md"
    assert os.path.exists(path), "pre-registration file missing"
    doc = open(path, encoding="utf-8").read().lower()
    for needle in ("inconclusive", "holm", "bonferroni",
                   "minimum detectable effect", "12/15", "3/4", "0.2r",
                   "exploratory", "block bootstrap"):
        assert needle in doc, f"preregistration missing: {needle}"
    print("PASS preregistration: outcomes/multiplicity/stable-positive "
          "committed before data")


if __name__ == "__main__":
    test_short_sweep_reclaim_cisd()
    test_long_mirror()
    test_fvg_scan_and_dead()
    test_sizing()
    test_no_reclaim_times_out()
    test_bias_symmetry()
    test_fvg_orientation_symmetry()
    test_partial_4h_bucket_discarded()
    test_4h_starttime_bucketing()
    test_consolidator_handler_slot_discipline()
    test_oco_single_exit_invariant()
    test_protocol_conformance()
    test_deterministic_replay()
    test_mirrored_cisd_reference()
    test_identity_gates_can_go_red()
    test_exit_time_algo_clock_and_drain()
    test_floor_params_in_read_list()
    test_e19b_candidates_post_reclaim()
    test_ft_export_is_one_exact_32bit_series()
    test_ft_export_preserves_event_time_and_uniquifies_collisions()
    test_ft_chart_added_after_points_for_snapshot_semantics()
    test_ft_export_stays_within_four_custom_charts()
    test_ft_series_reuses_existing_global_quota_name()
    test_ft_screen_probability_nondecreasing_in_stop_width()
    test_ft_screen_prices_same_bar_ambiguity_as_stop()
    test_ft_screen_reports_maximally_optimistic_ambiguity_bound()
    test_ft_screen_reports_driftless_barrier_benchmark()
    test_ft32e_committed_bounds_and_martingale_summary()
    test_ft_ledger_required_and_count_reconciled()
    test_ft_ledger_rejects_vacuous_zero_event_export()
    test_ft_monotonicity_rejects_vacuous_cells()
    test_ft_chart_read_polls_and_requests_declared_count()
    test_sync_file_compares_exact_bytes()
    test_ft_driver_main_uses_created_backtest_id()
    test_event_predicate_registry_and_exact_discovery_transport()
    test_default_predicate_preserves_legacy_experiment_identity()
    test_discovery_predicates_drive_real_reclaim_path()
    test_discovery_export_packs_family_mask_above_ft32()
    test_discovery_export_includes_opposed_arm_without_changing_legacy_ft32()
    test_random_time_control_reservoir_matches_risk_multiset_and_horizon()
    test_random_time_control_matches_source_date_and_exact_horizon_path()
    test_random_time_control_excludes_self_bar_and_rejects_path_gap()
    test_random_time_control_rejects_nonliteral_endpoint_seconds()
    test_random_time_control_sampling_identity_is_et_timezone_invariant()
    test_random_time_control_drives_real_consolidator_without_orders()
    test_random_time_control_spec_exactly_matches_committed_risk_distribution()
    test_random_control_driver_fail_closed_and_surface_identity()
    test_random_control_driver_rejects_off_grid_and_wrong_date_chart_x()
    test_random_control_launch_guard_allows_only_compile_id_after_compile()
    test_random_control_comparison_executes_all_three_frozen_branches()
    test_discovery_modules_are_byte_verified_deployment_sources()
    test_sync_snapshots_one_stable_multi_file_source_set()
    test_sync_source_reader_preserves_line_ending_bytes()
    test_reapply_validates_complete_committed_source_set_before_restore()
    test_reapply_rolls_back_whole_bundle_on_mid_replace_failure()
    test_reapply_retains_recovery_backups_when_rollback_fails()
    test_discovery_decoder_screens_each_matched_family()
    test_discovery_chart_read_polls_and_decodes_exact_declared_count()
    test_preregistration_present()
    print("ALL LOCAL CHRONOLOGY TESTS PASSED")
