"""Permanent tests for the C2 local-data guards (2026-09-04).

(a) date gate: session dates past DEV_END refuse to load unless the
    committed VALIDATION_UNLOCK flag is explicitly passed True.
    DateGateSelfAudit statically audits EVERY repo .py for call paths
    that could route around the gate (raw decode primitives, unlocked=
    literals, flag rebinding/mutation) and fails on any of them; a
    negative test proves the audit can go red.
(b) roll handling: the embedded roll (underlying symbol change under the
    continuous series) resets ATR and invalidates the partial overnight --
    proven by a roll-day price discontinuity that must NOT corrupt an
    overnight high/low, on synthetic AND on real purchased data.
(c) QuantConnect reconciliation: local Databento 30m bars must match
    QuantConnect Lean data. Two layers: the bundled Lean files (GC
    ordinary weekdays 2013-10) and the cloud extension
    (QcCloudReconciliation) that dumps NQ + GC ROLL windows and holiday
    sessions from LEAN itself via a short data-dump backtest (d49);
    skip-clean when the git-ignored purchase or dump fixtures are not
    on disk; run for real on the dev machine.

Synthetic-data tests (a) and (b) always run; (c) and the cloud
extension need purchased files / dump fixtures (see d49 docstring).
"""
import ast
import json
import os
import re
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import databento_local_data as dld  # noqa: E402
from event_generators import OvernightLevelTouchV1  # noqa: E402

UTC = timezone.utc


def _iid(symbol):
    """Deterministic stand-in instrument_id for synthetic fixtures (real
    rows always carry one): stable small int derived from the symbol."""
    return sum((i + 1) * ord(ch) for i, ch in enumerate(symbol))


def _minute_rows_from_bars(bars_spec):
    """bars_spec: (et_naive_start, symbol, o, h, l, c) 30m bars -> minutes.
    Naive datetimes are ET WALL-CLOCK times (what the generator consumes);
    they are stamped with the ET zone so ns timestamps round-trip."""
    rows = []
    for start, sym, o, h, l, c in bars_spec:
        ts0 = int(start.replace(tzinfo=dld.ET).timestamp() * 1e9)
        for k in range(30):
            rows.append({"ts_event_ns": ts0 + k * 60 * 1_000_000_000,
                         "instrument_id": _iid(sym), "cont_symbol": "X.n.0",
                         "symbol": sym, "open": o, "high": h, "low": l,
                         "close": c, "volume": 10})
    return rows


def _flat_minutes(start_et_naive, symbol, n_minutes, price=100.0,
                  volume=5):
    rows = []
    base = int(start_et_naive.replace(tzinfo=dld.ET).timestamp() * 1e9)
    for k in range(n_minutes):
        rows.append({"ts_event_ns": base + k * 60 * 1_000_000_000,
                     "instrument_id": _iid(symbol), "cont_symbol": "X.n.0",
                     "symbol": symbol, "open": price, "high": price,
                     "low": price, "close": price, "volume": volume})
    return rows


def _overnight_spec(td, sym, base=100.0, step=1.0):
    """31 contiguous overnight bars for trade date td: minute-starts 18:00
    prev-day through 09:00 (completed-bar ENDs 18:30 through 09:30)."""
    specs = []
    t = datetime.combine(td - timedelta(days=1), datetime.min.time()
                         ).replace(hour=18)
    for i in range(31):
        o = base
        c = base + step * i
        specs.append((t, sym, o, max(o, c) + 0.5, min(o, c) - 0.5, c))
        t += timedelta(minutes=30)
    return specs


def feed_generator(gen, minute_rows):
    """Pipeline contract: embedded rolls fire on_rollover BEFORE the first
    completed bar containing new-symbol minutes; bars flow otherwise.
    Returns the bars actually delivered."""
    bars, _mixed = dld.build_bars_30m(minute_rows)
    rolls = dld.detect_rolls(minute_rows)
    pending = list(rolls)
    for bar in bars:
        first_minute_ns = int((bar["et"] - timedelta(minutes=30)
                               ).replace(tzinfo=dld.ET).timestamp() * 1e9)
        while (pending
               and bar["symbol"] == pending[0]["new_symbol"]
               and pending[0]["ts_event_ns"] >= first_minute_ns
               - 1_000_000_000):
            r = pending.pop(0)
            gen.on_rollover(bar["et"], r["old_symbol"], r["new_symbol"])
            break
        gen.on_bar({"open": bar["open"], "high": bar["high"],
                    "low": bar["low"], "close": bar["close"],
                    "et": bar["et"]})
    return bars


class DateGate(unittest.TestCase):
    def test_refuses_validation_dates(self):
        with self.assertRaises(dld.DateGateError):
            dld.check_session_dates(
                {date(2024, 12, 31), date(2025, 1, 15)})

    def test_default_call_site_stays_locked(self):
        # forgetting the argument must never unlock by accident
        with self.assertRaises(dld.DateGateError):
            dld.check_session_dates([date(2026, 6, 1)])

    def test_allows_dev_dates(self):
        dld.check_session_dates({date(2010, 6, 7), date(2024, 12, 31)})

    def test_unlock_is_committed_and_explicit(self):
        # unlock only via the committed flag, never a truthy default
        self.assertFalse(dld.VALIDATION_UNLOCK,
                         "VALIDATION_UNLOCK must stay False in a committed "
                         "state until the preregistered validation phase")
        dld.check_session_dates([date(2025, 1, 15)], unlocked=True)

    def test_loader_refuses_days_past_gate(self):
        # second mechanism of guard (a): an explicit post-DEV_END day
        # request raises even though the file physically contains it
        # (skip when the purchase is not on disk)
        if not os.path.exists(dld.OHLCV_FILE):
            self.skipTest("purchase not on disk")
        with self.assertRaises(dld.DateGateError):
            dld.load_purchased_bars(days=[date(2025, 6, 2)])

    def test_raw_primitive_refuses_post_gate_members(self):
        # the gate must live at the primitive, not only the convenience
        # loader: asking for any UTC member past DEV_END raises unless
        # explicitly unlocked
        if not os.path.exists(dld.OHLCV_FILE):
            self.skipTest("purchase not on disk")
        with self.assertRaises(dld.DateGateError):
            dld.dbn_minute_rows(dld.OHLCV_FILE, "GC",
                                {dld.DEV_END + timedelta(days=1)})
        # a member AT the gate is fine (its rows' trade dates are checked
        # downstream, and the gate day itself is dev data)
        rows = dld.dbn_minute_rows(dld.OHLCV_FILE, "GC", {dld.DEV_END})
        self.assertTrue(all(dld.trade_date_of(
            dld.ts_to_et(r["ts_event_ns"])) <= dld.DEV_END
            or dld.trade_date_of(dld.ts_to_et(r["ts_event_ns"])
                                 ) == dld.DEV_END + timedelta(days=1)
            for r in rows))


class RollHandling(unittest.TestCase):
    def test_roll_resets_atr(self):
        gen = OvernightLevelTouchV1(tick_size=0.25)
        td = date(2024, 3, 15)
        feed_generator(gen, _minute_rows_from_bars(
            _overnight_spec(td, "NQH24")))
        self.assertTrue(gen._trs)
        gen.on_rollover(datetime(2024, 3, 15, 2, 0, tzinfo=UTC),
                        "NQH24", "NQM24")
        self.assertEqual(gen._trs, [])
        self.assertIsNone(gen._prev_close)

    def test_rollover_requires_distinct_contracts(self):
        gen = OvernightLevelTouchV1(tick_size=0.25)
        with self.assertRaises(ValueError):
            gen.on_rollover(datetime(2024, 3, 15, 2, 0, tzinfo=UTC),
                            "NQH24", "NQH24")

    def test_embedded_roll_detected_from_symbol_change(self):
        td = date(2024, 6, 10)
        specs = (_overnight_spec(td, "GCZ24", base=2350.0)[:10]
                 + _overnight_spec(td, "GCM24", base=2352.0)[10:])
        rolls = dld.detect_rolls(_minute_rows_from_bars(specs))
        self.assertEqual(len(rolls), 1)
        self.assertEqual(rolls[0]["old_symbol"], "GCZ24")
        self.assertEqual(rolls[0]["new_symbol"], "GCM24")
        self.assertEqual(rolls[0]["trade_date"], td)

    def test_stream_and_definition_views_agree(self):
        """Guard (b) explicitly requires detection from the DBN stream AND
        definition data: the session-level mapping view must report the
        same roll session the stream view found, no more and no less."""
        td = date(2024, 6, 10)
        specs = (_overnight_spec(td, "GCZ24", base=2350.0)[:10]
                 + _overnight_spec(td, "GCM24", base=2352.0)[10:])
        rows = _minute_rows_from_bars(specs)
        stream = dld.detect_rolls(rows)
        definition_view = dld.mapping_roll_sessions(rows)
        self.assertEqual(len(stream), 1)
        self.assertEqual(len(definition_view), 1)
        self.assertEqual(definition_view[0]["trade_date"],
                         stream[0]["trade_date"])
        self.assertEqual(definition_view[0]["old_instrument_id"],
                         stream[0]["old_instrument_id"])
        self.assertEqual(definition_view[0]["new_instrument_id"],
                         stream[0]["new_instrument_id"])
        # roll-free stream: both views empty, mapping table well-formed
        clean = _minute_rows_from_bars(_overnight_spec(td, "GCZ24"))
        self.assertEqual(dld.detect_rolls(clean), [])
        self.assertEqual(dld.mapping_roll_sessions(clean), [])
        tables, _r = dld.build_mapping_table(clean)
        self.assertEqual(tables["X.n.0"][td], _iid("GCZ24"))

    def test_roll_day_discontinuity_cannot_corrupt_levels(self):
        """The permanent guard-(b) proof.

        A clean first trade date (contract H) establishes overnight levels.
        On the roll trade date the stream switches H->M mid-overnight, and
        the OLD contract's bars sit 1000 points ABOVE the new one: if the
        invalidation ever failed, the inflated old-contract high could
        leak into an overnight range computed against new-contract prices.
        """
        gen = OvernightLevelTouchV1(tick_size=0.25)
        td1 = date(2024, 3, 15)
        feed_generator(gen, _minute_rows_from_bars(
            _overnight_spec(td1, "NQH24", base=18000.0)))
        self.assertTrue(gen._levels)
        self.assertIsNotNone(gen._atr())

        td2 = date(2024, 3, 18)
        split = 15  # roll lands mid-overnight (between bars 14 and 15)
        specs_h = _overnight_spec(td2, "NQH24", base=18000.0)
        specs_m = _overnight_spec(td2, "NQM24", base=17000.0)
        specs = specs_h[:split] + specs_m[split:]
        feed_generator(gen, _minute_rows_from_bars(specs))
        # the mapping event invalidated the partial overnight: NO levels
        self.assertIsNone(gen._levels,
                          "roll-trade-date overnight must yield no levels")

        # next trade date, fully new contract: levels come from NEW bars only
        td3 = date(2024, 3, 19)
        feed_generator(gen, _minute_rows_from_bars(
            _overnight_spec(td3, "NQM24", base=17000.0)))
        hi, lo = gen._levels
        self.assertLess(hi, 17100.0,
                        f"corruption: old-contract high leaked (hi={hi})")
        self.assertGreater(lo, 16900.0,
                           f"corruption: old-contract low leaked (lo={lo})")

    def test_zero_volume_minutes_do_not_fabricate_bars(self):
        # Lean has no bar for a no-trade minute; the local path must agree
        rows = _flat_minutes(datetime(2024, 5, 15, 9, 30), "GCZ24", 60,
                             volume=0)
        bars, mixed = dld.build_bars_30m(rows)
        self.assertEqual(bars, [])
        self.assertEqual(mixed, [])

    def test_mid_slot_roll_produces_no_bar(self):
        # a slot whose minutes span two contracts must be excluded (mixed),
        # never emitted as a cross-contract price blend
        rows = (_flat_minutes(datetime(2024, 5, 15, 9, 30), "GCZ24", 10)
                + _flat_minutes(datetime(2024, 5, 15, 9, 40), "GCM24", 10))
        rows[10]["high"] = 999.0
        bars, mixed = dld.build_bars_30m(rows)
        self.assertEqual(len(mixed), 1, "roll slot not recorded")
        self.assertEqual(mixed[0], datetime(2024, 5, 15, 10, 0),
                         "mixed slot must carry its completed-bar END time")
        for b in bars:
            self.assertNotIn(999.0, (b["high"], b["low"], b["open"],
                                     b["close"]),
                             "mixed-contract bar leaked into the stream")


class SymbolDecoding(unittest.TestCase):
    def test_raw_symbol_to_yyyymm(self):
        # 2-digit year, direct
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCZ24", 2024, 6),
                         "202412")
        self.assertEqual(dld.raw_symbol_to_yyyymm("NQH25", 2024, 11),
                         "202503")
        # 1-digit year resolved against the record's own reference
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCZ13", 2013, 10),
                         "201312")
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCZ3", 2013, 10),
                         "201312")
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCG4", 2024, 1),
                         "202402")
        # V = October; ref 2019-10 resolves to the same month: 201910
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCV9", 2019, 10),
                         "201910")
        # a code that has already expired vs ref month walks to next decade
        self.assertEqual(dld.raw_symbol_to_yyyymm("GCF9", 2019, 10),
                         "202901")


class QcReconciliation(unittest.TestCase):
    """Guard (c): local Databento bars vs the bundled QC Lean minutes.

    Join convention, established empirically on real Oct-2013 GC data:
    both paths are aggregated to 30m bars keyed on **trade date + ET
    wall-clock end time**. A QC trade file can omit a session's first
    evening minutes (they surface in the next day's file), so all three
    adjacent files are merged and filtered by trade date — under this
    convention 47/47 bars align with ZERO orphans on every sample day.
    Sample = four full weekdays (Tue-Fri 2013-10-08..11): Sunday 10-07 is
    excluded because the git-ignored bundle's 20131007 file starts at
    21:22 ET, missing the Globex evening-reopen minutes DBN carries from
    18:00 — a bundle boundary, not a pipeline defect; Campaign 1's
    population is weekday sessions anyway.

    MEASURED CONTRACT (4 days, 188 common bars — all numbers below are
    measured, not aspirational):
      - high/low within ONE tick on every bar (363/376 field comparisons
        exact) — these build overnight levels and drive touch triggers;
      - open/close within FOUR ticks (measured worst case: one Friday
        16:30 bar-open, Databento first-trade 1270.0 vs AlgoSeek 1270.4);
        `open` is never consumed by the frozen generator at all;
      - full OHLC exact on >=60% of bars (measured 65.4%);
      - root cause of residual drift: Databento GLBX.MDP3 consolidates
        CME Globex + CME ClearPort, Lean's bundle is the AlgoSeek feed —
        day volume ratio ~1.7:1. Bit-exact equality is impossible across
        vendors; the tick ceilings are the meaningful equivalence.
    Any violation fails with printed evidence. The hosted path remains
    the compute authority and the byte-exact generator_v1 gate the
    methodology anchor; this test BOUNDS the local path's equivalence
    instead of silently assuming it. NQ has no LOCAL bundle coverage
    (the bundle holds es only) — its reconciliation, and every ROLL
    window, moved to the cloud extension below
    (QcCloudReconciliation, fed by d49 dump backtests). ES remains a
    documented extension point: named, never reconciled.
    """

    SAMPLE_DAYS = [date(2013, 10, 8), date(2013, 10, 9),
                   date(2013, 10, 10), date(2013, 10, 11)]
    GC_TICK = 0.10
    MAX_HL_DEV_TICKS = 1
    MAX_OC_DEV_TICKS = 4
    MIN_FULL_EXACT_FRACTION = 0.60
    # front GC expiry through the whole sample window (V13 rolled ~Oct 29)
    SAMPLE_EXPIRY = "201312"

    def _qc_trade_rows(self, days_around, expiry):
        rows = []
        for f in days_around:
            p = os.path.join(dld.QC_FUTURE_DIR, "comex", "minute", "gc",
                             f"{f.strftime('%Y%m%d')}_trade.zip")
            if os.path.exists(p):
                rows += dld.qc_minute_bars("comex", "gc",
                                           f.strftime("%Y%m%d"),
                                           expiry_filter=expiry)
        rows.sort(key=lambda r: r["ts_event_ns"])
        return rows

    def test_gc_sample_days_match(self):
        if not os.path.exists(dld.OHLCV_FILE):
            self.skipTest("databento purchase not on disk (data/ is "
                          "git-ignored); run d48 first")
        if not os.path.exists(dld.DEFINITION_FILE):
            self.skipTest("definition container not on disk; run d48 first")
        instrument_map = dld.load_instrument_map()
        totals = {"bars": 0, "exact": 0}
        checked_days = 0
        for day in self.SAMPLE_DAYS:
            # DBN side: members {D-1, D}; rows whose TRADE DATE == D
            rows_w = dld.dbn_minute_rows(
                dld.OHLCV_FILE, "GC", {day - timedelta(days=1), day})
            rows = [r for r in rows_w
                    if dld.trade_date_of(dld.ts_to_et(r["ts_event_ns"])
                                         ) == day]
            self.assertTrue(rows, f"no DBN GC rows for trade date {day}")
            iids = {r["instrument_id"] for r in rows}
            self.assertEqual(len(iids), 1,
                             f"{day} unexpectedly straddles a roll: {iids}")
            iid = next(iter(iids))
            raw = dld.resolve_raw_symbol(instrument_map, iid, day)
            expiry = dld.raw_symbol_to_yyyymm(raw, day.year, day.month)
            self.assertEqual(expiry, self.SAMPLE_EXPIRY,
                             f"{day}: definition says {raw} -> {expiry}, "
                             "sample window assumed front 201312")
            dbn_bars = dld.build_bars_30m(rows)[0]
            # QC side: merge files {D-1, D, D+1}, same trade-date filter
            qc_bars = dld.build_bars_30m(self._qc_trade_rows(
                (day - timedelta(days=1), day, day + timedelta(days=1)),
                {expiry}))[0]
            qc_bars = [b for b in qc_bars
                       if dld.trade_date_of(b["et"]) == day]
            dbn_by = {b["et"]: b for b in dbn_bars}
            qc_by = {b["et"]: b for b in qc_bars}
            common = sorted(set(dbn_by).intersection(qc_by))
            self.assertGreater(len(common), 40,
                               f"{day}: only {len(common)} common bars — "
                               "alignment lost")
            self.assertEqual(
                sorted(set(dbn_by) - set(qc_by)), [],
                f"{day} dbn-only bars: {sorted(set(dbn_by)-set(qc_by))[:6]}")
            self.assertEqual(
                sorted(set(qc_by) - set(dbn_by)), [],
                f"{day} qc-only bars: {sorted(set(qc_by)-set(dbn_by))[:6]}")
            violations = []
            for et in common:
                a, b = dbn_by[et], qc_by[et]
                for k in ("open", "close"):
                    if abs(a[k] - b[k]) > self.MAX_OC_DEV_TICKS \
                            * self.GC_TICK * 1.001:
                        violations.append(
                            (et, k, a[k], b[k], self.MAX_OC_DEV_TICKS))
                for k in ("high", "low"):
                    if abs(a[k] - b[k]) > self.MAX_HL_DEV_TICKS \
                            * self.GC_TICK * 1.001:
                        violations.append(
                            (et, k, a[k], b[k], self.MAX_HL_DEV_TICKS))
                if all(round(a[k], 4) == round(b[k], 4)
                       for k in ("open", "high", "low", "close")):
                    totals["exact"] += 1
            totals["bars"] += len(common)
            self.assertEqual(
                violations, [],
                f"{day} {raw} (qc {expiry}) measured-contract violations "
                f"(et, field, dbn, qc, ceiling-ticks): {violations[:8]}")
            checked_days += 1
        self.assertEqual(checked_days, len(self.SAMPLE_DAYS),
                         "fewer QC sample days found on disk than expected")
        fraction = totals["exact"] / totals["bars"]
        self.assertGreaterEqual(
            fraction, self.MIN_FULL_EXACT_FRACTION,
            f"only {totals['exact']}/{totals['bars']} bars fully exact "
            f"(< {self.MIN_FULL_EXACT_FRACTION:.0%} measured floor)")
        print(f"QC-reconciliation guard(c): {totals['bars']} common bars "
              f"across {checked_days} days, {totals['exact']} fully exact "
              f"({fraction:.1%}), H/L within "
              f"{self.MAX_HL_DEV_TICKS} tick, O/C within "
              f"{self.MAX_OC_DEV_TICKS} ticks, zero orphan bars")


def _load_cloud_fixture(tag):
    """Read a d49-produced dump fixture (git-ignored: vendor bar data is
    never committed to the public repo; regenerate with
    `python d49_nq_dump_cloud.py <tag>`). Returns (bars, runtime_stats)
    with bars keyed by naive-ET end datetime.
    """
    path = os.path.join(dld.DATA_DIR, f"dump_{tag}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        fx = json.load(fh)
    bars = {datetime.fromisoformat(b["et"]): b for b in fx["bars"]}
    return bars, fx["runtimeStatistics"]


def _parse_roll_events(rt):
    """b5_rolls: 'minute_ET_ISO=NEW>OLD|...' -> [(et, new_token, old_token)]"""
    raw = rt.get("b5_rolls", "none")
    if raw in ("none", "", None):
        return []
    out = []
    for part in raw.split("|"):
        stamp, _, pair = part.partition("=")
        new, _, old = pair.partition(">")
        out.append((datetime.fromisoformat(stamp), new, old))
    return out


class QcCloudReconciliation(unittest.TestCase):
    """Guard (c), cloud extension (2026-09-04): the GC-only bundle test
    could not see NQ (the bundle holds es only) and could not see any
    ROLL window. These tests reconcile the local Databento pipeline
    bar-for-bar against QuantConnect LEAN itself — one short data-dump
    backtest (c2_nq_dump_main.py via d49) over windows chosen to contain
    a contract roll AND a market holiday, per market.

    MEASURED contract (all four windows; fixtures regenerate via d49):
      - When both vendors sit on the SAME contract for a bar's whole
        slot, OHLC is BIT-EXACT on ~97-100% of shared bars and within
        1 tick H/L + 4 tick O/C on every other shared bar (measured
        residuals are the same first-trade/settlement-print drift the
        2013 GC bundle test characterizes).
      - Window-edge slots (the first session's bars whose minutes
        predate the cloud backtest's start date) and the vendor-local
        MIXED roll slot are excluded on principle, not by list: they
        are boundary artifacts, not OHLC disagreements.
      - ROLL TIMING IS A GENUINE VENDOR DISAGREEMENT and is asserted
        as measured, never papered over:
          * NQ 2024: Databento OI rolled Z4->H5 at 2024-12-18 19:00 ET
            (trade session 2024-12-19); LEAN OPEN_INTEREST fired its
            mapping event at 2024-12-19 00:00 ET — SAME trade session,
            and every other day of the window is bit-exact.
          * GC 2020: Databento OI rolled G0->J0 at 2020-01-23 19:00 ET
            (session 2024-01-24); LEAN's depth-0 series did NOT change
            until its events of 2020-02-06/07 — a ~2-week divergence in
            which each vendor legitimately held a different front month.
            Before the divergence and again from 2020-02-10, every bar
            matches its same-contract local twin BIT-EXACTLY (46/46,
            max diff 0.00) — the disagreement is in the rule's clock,
            not in bar arithmetic.
        The study consumes the LOCAL pipeline; both paths fail-close
        the affected sessions' overnights (mixed slot -> contiguity
        gap -> no event; on_rollover reset), so the divergence cannot
        corrupt an overnight range — see RollDiscontinuityCannotCorrupt.
    """

    TICK = {"NQ": 0.25, "GC": 0.10}
    MAX_HL_DEV_TICKS = 1
    MAX_OC_DEV_TICKS = 4

    def _local_bars(self, market, day, contract=None):
        imap = dld.load_instrument_map()
        mf = dld.widen_member_days({day}) & dld.available_days()
        rows = dld.dbn_minute_rows(dld.OHLCV_FILE, market, mf,
                                   instrument_map=imap)
        rows = [r for r in rows if dld.trade_date_of(
            dld.ts_to_et(r["ts_event_ns"])) == day]
        if contract is not None:
            rows = [r for r in rows if r["symbol"] == contract]
        bars, _mixed = dld.build_bars_30m(rows)
        return {b["et"]: b for b in bars}

    def _tick_contract(self, bars_c, market, start_boundary, tag):
        """Compare shared slots; window-edge slots and mixed roll slots
        excluded on principle. Returns (n_compared, violations)."""
        tick = self.TICK[market]
        violations = []
        n = 0
        days = sorted({dld.trade_date_of(t) for t in bars_c})
        for day in days:
            loc = self._local_bars(market, day)
            for et, cb in sorted(bars_c.items()):
                if dld.trade_date_of(et) != day:
                    continue
                slot_start = et - timedelta(minutes=30)
                if slot_start < start_boundary:
                    continue          # window-edge: cloud never saw the
                lb = loc.get(et)      # slot's early minutes
                if lb is None:
                    continue          # local mixed-roll slot or orphan
                n += 1
                for f, k in (("h", "high"), ("l", "low")):
                    if abs(cb[f] - lb[k]) > self.MAX_HL_DEV_TICKS * tick \
                            * 1.001:
                        violations.append((str(et), f, cb[f], lb[k]))
                for f, k in (("o", "open"), ("c", "close")):
                    if abs(cb[f] - lb[k]) > self.MAX_OC_DEV_TICKS * tick \
                            * 1.001:
                        violations.append((str(et), f, cb[f], lb[k]))
        self.assertGreater(n, 300,
                           f"{tag}: only {n} comparable bars — the join "
                           "silently lost its population")
        return n, violations

    def setUp(self):
        if not os.path.exists(dld.OHLCV_FILE):
            self.skipTest("databento purchase not on disk")
        if not os.path.exists(dld.DEFINITION_FILE):
            self.skipTest("definition container not on disk")

    def _fixture_or_skip(self, tag):
        fx = _load_cloud_fixture(tag)
        if fx is None:
            self.skipTest(f"dump fixture {tag} missing — regenerate with "
                          f"python d49_nq_dump_cloud.py {tag}")
        # guard (a) extends to the cloud transport: a dump fixture must
        # never contain a validation/holdout session, no matter what
        # window someone re-runs later.
        leaked = [t for t in fx[0] if dld.trade_date_of(t) > dld.DEV_END]
        self.assertEqual(leaked, [],
                         f"{tag}: fixture contains post-DEV_END sessions "
                         f"{leaked[:4]} — dump window is no longer dev-only")
        return fx

    def test_nq_holiday_window(self):
        bars, rt = self._fixture_or_skip("nq-holiday")
        self.assertEqual(rt["dump_instrument"], "NQ")
        n, violations = self._tick_contract(
            bars, "NQ", datetime(2024, 11, 15, 0, 0), "nq-holiday")
        self.assertEqual(violations, [],
                         f"nq-holiday tick-contract violations: "
                         f"{violations[:8]}")
        # Thanksgiving 2024-11-28 (Thursday): the CME equity-index
        # early-close day inside this window. A normal weekday carries
        # 46 completed 30m bars (session 18:30 prev .. 17:00 ET);
        # 0 < n < 46 proves the holiday calendar is exercised, and the
        # local path must agree bar-for-bar with the cloud on it (the
        # tick-contract loop above already compared Nov 28 and 29).
        self.assertIn("2024-11-28", rt["b5_days"])
        n_1128 = sum(1 for t in bars if dld.trade_date_of(t)
                     == date(2024, 11, 28))
        self.assertGreater(n_1128, 0)
        self.assertLess(n_1128, 46,
                        "Thanksgiving should be early-closed, not a "
                        "full session — if the calendar changed, "
                        "re-measure")
        # no roll events expected or allowed in this window
        self.assertEqual(_parse_roll_events(rt), [])
        print(f"cloud-recon nq-holiday: {n} bars within tick contract "
              "(zero violations); holiday session present; zero rolls")

    def test_nq_roll_window(self):
        bars, rt = self._fixture_or_skip("nq-roll")
        # holiday coverage INSIDE the roll window (the directive's
        # single 2-week window must contain BOTH): Christmas Eve 2024
        # session early-closed (<46 bars), Christmas 2024-12-25 session
        # absent entirely (Globex closed; no evening reopen Dec 24).
        self.assertIn("2024-12-24", rt["b5_days"])
        n_1224 = sum(1 for t in bars if dld.trade_date_of(t)
                     == date(2024, 12, 24))
        self.assertGreater(n_1224, 0)
        self.assertLess(n_1224, 46, "Christmas Eve must be early-closed")
        self.assertNotIn("2024-12-25", rt["b5_days"],
                         "Christmas session must carry no bars (closed)")
        self.assertGreater(
            sum(1 for t in bars if dld.trade_date_of(t)
                == date(2024, 12, 27)), 40,
            "post-holiday session 2024-12-27 should be (nearly) full")
        events = _parse_roll_events(rt)
        self.assertEqual(len(events), 1,
                         f"expected exactly one NQ mapping event in the "
                         f"roll window, got {events}")
        event_et = events[0][0]
        # MEASURED divergence: Databento rolled at 2024-12-18 19:00 ET;
        # LEAN fired 2024-12-19 00:00 — assert same-trade-session, then
        # assert every slot OUTSIDE that session satisfies the contract.
        self.assertEqual(dld.trade_date_of(event_et), date(2024, 12, 19))
        imap = dld.load_instrument_map()
        mf = dld.widen_member_days({date(2024, 12, 19)}) & \
            dld.available_days()
        local_rows = dld.dbn_minute_rows(dld.OHLCV_FILE, "NQ", mf,
                                         instrument_map=imap)
        local_rolls = dld.detect_rolls(local_rows)
        self.assertEqual(len(local_rolls), 1)
        local_et = dld.ts_to_et(local_rolls[0]["ts_event_ns"])
        self.assertEqual((local_et, event_et.hour),
                         (datetime(2024, 12, 18, 19, 0), 0))
        self.assertEqual(dld.trade_date_of(local_et),
                         dld.trade_date_of(event_et),
                         "roll sessions must agree even when the exact "
                         "minute is a documented vendor divergence")
        # contract everywhere except the divergence session's rolled-off
        # evening: bars whose slot begins at/after the local roll minute
        # AND before the cloud event belong to two different contracts
        # and are excluded as ROLL-DIVERGENT, not as failures.
        n = 0
        violations = []
        for day in sorted({dld.trade_date_of(t) for t in bars}):
            loc = self._local_bars("NQ", day)
            for et, cb in sorted(bars.items()):
                if dld.trade_date_of(et) != day:
                    continue
                if et - timedelta(minutes=30) < datetime(2024, 12, 16):
                    continue
                if day == date(2024, 12, 19):
                    continue  # divergence session, checked exactly below
                lb = loc.get(et)
                if lb is None:
                    continue
                n += 1
                for f, k in (("h", "high"), ("l", "low")):
                    if abs(cb[f] - lb[k]) > self.MAX_HL_DEV_TICKS * 0.25 \
                            * 1.001:
                        violations.append((str(et), f, cb[f], lb[k]))
                for f, k in (("o", "open"), ("c", "close")):
                    if abs(cb[f] - lb[k]) > self.MAX_OC_DEV_TICKS * 0.25 \
                            * 1.001:
                        violations.append((str(et), f, cb[f], lb[k]))
        self.assertGreater(n, 350)
        self.assertEqual(violations, [],
                         f"nq-roll: non-divergence days must satisfy the "
                         f"tick contract: {violations[:8]}")
        # the divergence itself is MEASURED and bounded: on session
        # 2024-12-19 exactly the slots between the two vendors' roll
        # points differ, by the Z4/H5 calendar spread, and both paths
        # agree bit-exact on every other day. Count divergent slots.
        loc19 = self._local_bars("NQ", date(2024, 12, 19))
        divergent = [et for et, cb in bars.items()
                     if dld.trade_date_of(et) == date(2024, 12, 19)
                     and et in loc19
                     and abs(cb["c"] - loc19[et]["close"]) > 0.25 * 4.001]
        self.assertTrue(divergent,
                        "expected the measured Dec-19 roll divergence to "
                        "be present — if the fixtures changed, re-measure")
        print(f"cloud-recon nq-roll: {n} contract bars outside the "
              f"divergence session, zero violations; {len(divergent)} "
              f"roll-divergent slots session 2024-12-19 (Z4-vs-H5, "
              f"Databento 12-18 19:00 vs LEAN 12-19 00:00 event)")

    def test_gc_roll_window_cloud_divergence(self):
        bars_a, rt_a = self._fixture_or_skip("gc-roll")
        bars_b, rt_b = self._fixture_or_skip("gc-roll-b")
        self.assertEqual(rt_a["dump_instrument"], "GC")
        # MEASURED: zero LEAN mapping events through 2020-01-31 while
        # the Databento stream rolled G0->J0 at 2020-01-23 19:00.
        self.assertEqual(_parse_roll_events(rt_a), [],
                         "LEAN fired no GC event inside Jan-2020; if it "
                         "now does, re-measure the divergence")
        events_b = _parse_roll_events(rt_b)
        self.assertTrue(events_b,
                        "LEAN's GC mapping events must appear in early "
                        "Feb (measured 2020-02-06/07)")
        # holiday coverage: MLK Day 2020-01-20 session is early-closed
        # (measured 12 bars vs 46 normal) and Black-Friday-style Jan 17
        # evening opens it — the holiday calendar must exist in the
        # cloud dump too, not only locally.
        n_mlk = sum(1 for t in bars_a if dld.trade_date_of(t)
                    == date(2020, 1, 20))
        self.assertGreater(n_mlk, 0)
        self.assertLess(n_mlk, 46, "MLK Day must be early-closed")
        first_cloud_roll = min(e[0] for e in events_b)
        self.assertGreater(first_cloud_roll, datetime(2020, 2, 1))
        # before Databento's roll both paths sit on GCG0 and must match
        # BIT-EXACTLY bar-for-bar (measured 46/46, max diff 0.00)
        pre_days = [d for d in sorted({dld.trade_date_of(t)
                                       for t in bars_a})
                    if date(2020, 1, 21) <= d <= date(2020, 1, 23)]
        checked = 0
        for day in pre_days:
            loc = self._local_bars("GC", day, contract="GCG0")
            for et, cb in sorted(bars_a.items()):
                if dld.trade_date_of(et) != day or et - timedelta(
                        minutes=30) < datetime(2020, 1, 15):
                    continue
                lb = loc.get(et)
                if lb is None:
                    continue
                for f, k in (("o", "open"), ("h", "high"),
                             ("l", "low"), ("c", "close")):
                    self.assertAlmostEqual(cb[f], lb[k], delta=1e-9,
                                           msg=f"pre-roll GC {et} {f}")
                checked += 1
        self.assertGreater(checked, 100)
        # after the cloud's final mapping event both sit on GCJ0 and
        # match BIT-EXACTLY again (measured from 2020-02-10)
        checked = 0
        for day in [date(2020, 2, 10), date(2020, 2, 11), date(2020, 2, 12),
                    date(2020, 2, 13), date(2020, 2, 14)]:
            loc = self._local_bars("GC", day, contract="GCJ0")
            for et, cb in sorted(bars_b.items()):
                if dld.trade_date_of(et) != day:
                    continue
                lb = loc.get(et)
                if lb is None:
                    continue
                for f, k in (("o", "open"), ("h", "high"),
                             ("l", "low"), ("c", "close")):
                    self.assertAlmostEqual(cb[f], lb[k], delta=1e-9,
                                           msg=f"post-roll GC {et} {f}")
                checked += 1
        self.assertGreater(checked, 200,
                           "post-convergence bit-exactness lost")
        print(f"cloud-recon gc-roll: {checked} pre+post bars BIT-EXACT; "
              f"Databento rolled 2020-01-23 19:00, LEAN events from "
              f"{first_cloud_roll} — ~2-week front-month divergence, "
              "asserted as measured")

    def test_roll_discontinuity_cannot_corrupt_levels_real_data(self):
        """The directive's central fear, asserted end-to-end on REAL
        purchased + cloud-reconciled data: a roll must never produce an
        overnight range that mixes two contracts.

        The GC embedded roll (GCG0->GCJ0, first new-contract minute
        2020-01-23 19:00 ET) sits INSIDE the overnight of trade session
        2020-01-24. Two facts make this the sharpest possible case:
        the switch lands exactly on a half-hour boundary (19:00), so
        build_bars_30m sees NO mixed slot — the ONLY thing standing
        between a two-contract overnight range and a published event is
        the on_rollover invalidation itself. And on these dates the two
        contracts traded ~6.5 points (~65 ticks) apart, so a leaked
        old-contract high/low would corrupt levels far beyond any
        vendor tolerance.

        Asserts:
          1. exactly one roll in the window, at the measured minute;
          2. NO event is published for session 2020-01-24 — the roll
             session's partial overnight is invalidated;
          3. every event that IS published has its reference level
             equal to a single-contract overnight high/low — computed
             independently from the same rows and compared exactly.
        """
        imap = dld.load_instrument_map()
        days = [date(2020, 1, 20) + timedelta(days=k) for k in range(18)]
        mf = dld.widen_member_days(set(days)) & dld.available_days()
        rows = dld.dbn_minute_rows(dld.OHLCV_FILE, "GC", mf,
                                   instrument_map=imap)
        rolls = dld.detect_rolls(rows)
        self.assertEqual(len(rolls), 1)
        roll_et = dld.ts_to_et(rolls[0]["ts_event_ns"])
        self.assertEqual(roll_et, datetime(2020, 1, 23, 19, 0))
        self.assertEqual(rolls[0]["old_symbol"], "GCG0")
        self.assertEqual(rolls[0]["new_symbol"], "GCJ0")

        class Capturing(OvernightLevelTouchV1):
            def __init__(self, tick_size):
                super().__init__(tick_size)
                self.captured = []

            def on_bar(self, row):
                events = super().on_bar(row)
                self.captured.extend(events)
                return events

        # run through the PERMANENT pipeline contract helper itself —
        # the same feed_generator every other test uses, so this proof
        # cannot drift from the contract.
        gen = Capturing(self.TICK["GC"])
        bars = feed_generator(gen, rows)
        events = gen.captured

        # (2) the roll session publishes nothing: partial overnight dies
        roll_session = dld.trade_date_of(roll_et)  # 2020-01-24
        on_roll_session = [ev for ev in events
                           if ev[4]["session_date"] == str(roll_session)]
        self.assertEqual(on_roll_session, [],
                         f"events leaked on the invalidated roll session "
                         f"{roll_session}: {on_roll_session}")

        # (3) every surviving event's level = a SINGLE-CONTRACT range
        bars_by_day = {}
        for b in bars:
            bars_by_day.setdefault(dld.trade_date_of(b["et"]), []).append(b)
        self.assertTrue(events, "expected GC events in this window")
        for ev in events:
            et, _side, level, _atr, ctx = ev
            td = dld.trade_date_of(et)
            # overnight bars: 18:30 previous day .. 09:30 trade date
            ob = [b for b in bars_by_day.get(td, [])
                  if (b["et"].hour > 18 or b["et"].hour < 9
                      or (b["et"].hour == 9 and b["et"].minute == 30)
                      or (b["et"].hour == 18 and b["et"].minute == 30))]
            contracts = {b["symbol"] for b in ob}
            self.assertEqual(len(contracts), 1,
                             f"event {et} overnight spans contracts "
                             f"{contracts} — corruption path open")
            hi = max(b["high"] for b in ob)
            lo = min(b["low"] for b in ob)
            want = hi if ctx["level_kind"] == "overnight_high" else lo
            self.assertAlmostEqual(level, want, delta=1e-9,
                                   msg=f"event {et}: level {level} != "
                                       f"single-contract {ctx['level_kind']} "
                                       f"{want}")
        print(f"cloud-recon roll-corruption: roll {roll_et} (65-tick "
              f"contract gap) invalidated session {roll_session} — "
              f"zero events there; {len(events)} events elsewhere all "
              "single-contract-verified")


class DateGateSelfAudit(unittest.TestCase):
    """The directive's lock: guard (a) must hold not because today's
    loaders check, but because NO future call path can route around the
    check unnoticed. This test statically audits every repo .py file."""

    REPO = dld.REPO_ROOT
    # Files permitted to touch the decode primitives at all.
    READER_ALLOWLIST = {"databento_local_data.py",
                        "test_databento_local_guards.py"}
    # unlocked=True outside these files is a violation: the gate module
    # itself (it forwards the caller-supplied flag) and the permanent
    # tests (which must DEMONSTRATE the unlocked path exists and is
    # reachable only via a committed flag). The negative test below
    # proves everything else is caught.
    UNLOCK_ALLOWLIST = {"databento_local_data.py",
                        "test_databento_local_guards.py"}
    # The committed flag must never be REASSIGNED or MUTATED anywhere,
    # except its single definition inside the gate module.
    GATE_MODULE = "databento_local_data.py"
    DECODE_TOKENS = ("dbn_minute_rows", "iter_dbn_frames",
                     "DBNStore", "read_dbn", ".to_df(")

    def _py_files(self):
        out = []
        for name in sorted(os.listdir(self.REPO)):
            if name.endswith(".py"):
                out.append(os.path.join(self.REPO, name))
        return out

    @staticmethod
    def _unlocked_literal_lines(tree):
        """Call sites where unlocked= is a literal True or any
        expression other than the committed VALIDATION_UNLOCK name
        (attribute form allowed: dld.VALIDATION_UNLOCK). Returns
        [(lineno, source-line)]."""
        def is_flag(node):
            if isinstance(node, ast.Name):
                return node.id == "VALIDATION_UNLOCK"
            if isinstance(node, ast.Attribute):
                return node.attr == "VALIDATION_UNLOCK"
            return False

        hits = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg == "unlocked" and not is_flag(kw.value):
                        hits.append(node.lineno)
        return hits

    @staticmethod
    def _flag_write_nodes(tree):
        """AST nodes that WRITE the committed flag anywhere other than
        a sanctioned definition. Returns [(lineno, kind)]."""
        hits = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) \
                    else [node.target]
                for tgt in targets:
                    if isinstance(tgt, ast.Name) \
                            and tgt.id == "VALIDATION_UNLOCK":
                        hits.append((node.lineno, "rebind"))
                    elif isinstance(tgt, ast.Attribute) \
                            and tgt.attr == "VALIDATION_UNLOCK":
                        hits.append((node.lineno, "attribute-mutation"))
                    elif isinstance(tgt, ast.Subscript):
                        key = tgt.slice
                        key = key.value if isinstance(key, ast.Constant) \
                            else key
                        base = tgt.value
                        if isinstance(key, ast.Constant) \
                                and key.value == "VALIDATION_UNLOCK" \
                                and isinstance(base, ast.Call) \
                                and getattr(base.func, "id", "") \
                                == "globals":
                            hits.append((node.lineno, "globals-mutation"))
        return hits

    def _audit(self, files):
        """Return a list of human-readable violations for one file set."""
        violations = []
        for path in files:
            name = os.path.basename(path)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            lines = text.splitlines()
            tree = ast.parse(text)
            # (1) decode primitives only inside the allowlist
            for tok in self.DECODE_TOKENS:
                if tok in text and name not in self.READER_ALLOWLIST:
                    violations.append(
                        f"{name}: touches decode primitive {tok!r} but is "
                        "not on READER_ALLOWLIST — route through "
                        "session_rows/load_purchased_bars or register "
                        "this file with review")
            # (2) unlocked=True may only appear in sanctioned files
            for i, line in enumerate(lines, 1):
                if re.search(r"unlocked\s*=\s*True", line) \
                        and name not in self.UNLOCK_ALLOWLIST:
                    violations.append(
                        f"{name}:{i}: passes unlocked=True outside the "
                        "unlock allowlist")
            # (3) outside allowlisted files, every unlocked= call
            # argument must be the committed flag itself (AST-level,
            # comment- and string-proof)
            if name not in self.UNLOCK_ALLOWLIST:
                for ln in self._unlocked_literal_lines(tree):
                    src = lines[ln - 1]
                    if re.search(r"unlocked\s*=\s*(dld\.)?"
                                 r"VALIDATION_UNLOCK\b", src):
                        continue
                    violations.append(
                        f"{name}:{ln}: unlocked= receives a non-flag "
                        f"expression: {src.strip()[:70]}")
            # (4) the committed flag is write-once at its definition,
            # and nobody may rebind/mutate it (AST Assign scan)
            for ln, kind in self._flag_write_nodes(tree):
                if kind == "rebind" and name == self.GATE_MODULE \
                        and ln == self._definition_line(text):
                    continue          # the sanctioned definition
                violations.append(
                    f"{name}:{ln}: {kind} of VALIDATION_UNLOCK outside "
                    "the sanctioned definition")
        return violations

    @staticmethod
    def _definition_line(text):
        for i, line in enumerate(text.splitlines(), 1):
            if re.match(r"^VALIDATION_UNLOCK\s*=", line):
                return i
        return -1

    def test_repository_has_no_bypass(self):
        violations = self._audit(self._py_files())
        self.assertEqual(violations, [],
                         "date-gate self-audit FAIL:\n" +
                         "\n".join(violations))
        # allowlists must not ROT: every entry must still be doing the
        # thing that earned its place, or the list shrinks in the same
        # commit that removes the behavior.
        names = {os.path.basename(p) for p in self._py_files()}
        self.assertTrue(self.READER_ALLOWLIST <= names)
        self.assertTrue(self.UNLOCK_ALLOWLIST <= names)
        text_gate = open(os.path.join(self.REPO, self.GATE_MODULE),
                         encoding="utf-8").read()
        self.assertIn("VALIDATION_UNLOCK = False", text_gate,
                      "the gate's committed default must stay False in "
                      "the file the audit reads")

    def test_audit_actually_catches_a_bypass(self):
        """Negative test (campaign rule: a gate never seen failing proves
        nothing): construct each bypass in a scratch file and show the
        audit goes RED on it."""
        scratch = {
            "bypass_decode.py": "import databento_local_data as dld\n"
                                "rows = dld.dbn_minute_rows("
                                "dld.OHLCV_FILE, 'GC', {dld.DEV_END})\n",
            "bypass_unlock.py": "import databento_local_data as dld\n"
                                "rows = dld.session_rows('GC', unlocked="
                                "True)\n",
            "bypass_mutation.py": "import databento_local_data as dld\n"
                                  "dld.VALIDATION_UNLOCK = True\n",
        }
        paths = []
        try:
            for name, src in scratch.items():
                p = os.path.join(self.REPO, name)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(src)
                paths.append(p)
                v = self._audit([p])
                self.assertTrue(v, f"audit FAILED to catch {name}")
        finally:
            for p in paths:
                os.remove(p)

    def test_gate_module_checks_before_decode(self):
        """Ordering proof at the primitive: in dbn_minute_rows the
        DateGateError raise must come BEFORE any iter_dbn_frames call —
        the check is not a post-hoc filter that could be reordered."""
        path = os.path.join(self.REPO, "databento_local_data.py")
        src = open(path, encoding="utf-8").read()
        i = src.index("def dbn_minute_rows")
        body = src[i:i + src[i:].index("\ndef ")]
        self.assertLess(body.index("DateGateError"),
                        body.index("iter_dbn_frames"))
        j = src.index("def session_rows")
        body2 = src[j:j + src[j:].index("\ndef ")]
        self.assertLess(body2.index("check_session_dates"),
                        body2.index("dbn_minute_rows(path"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
