"""Campaign-2 pure chronology and feasibility tests."""
from datetime import datetime, timedelta
import json
import hashlib


def bar(et, o, h, l, c):
    return {"et": et, "open": float(o), "high": float(h),
            "low": float(l), "close": float(c)}


def overnight_bars(session_date, high=110.0, low=90.0):
    """Exact 31 completed 30m bars ending 18:30..09:30 ET."""
    start = datetime.combine(session_date - timedelta(days=1),
                             datetime.min.time()).replace(hour=18, minute=30)
    rows = []
    for i in range(31):
        et = start + timedelta(minutes=30 * i)
        rows.append(bar(et, 100, high if i == 8 else 105,
                        low if i == 17 else 95, 100))
    return rows


def test_event_tuple_contract_and_generator_v1_frozen_artifacts():
    from event_generators import EventGenerator, SweepReclaimGeneratorV1
    assert EventGenerator.validate_event((datetime(2024, 1, 2, 10), -1,
                                          100.0, 4.0, {"x": 1}))
    g = SweepReclaimGeneratorV1()
    event = g.from_reclaim(datetime(2024, 1, 2, 10), 1, 99.0,
                           100.0, 96.0, {"bias_aligned": True})
    assert event == (datetime(2024, 1, 2, 10), 1, 99.0, 4.0,
                     {"bias_aligned": True})
    report = g.verify_frozen_e19br("e19br_ft_ledger")
    assert report["rows"] == 1121
    assert report["markets"] == {"NQ": 388, "ES": 186,
                                  "YM": 376, "RTY": 171}
    assert report["byte_exact"] is True


def test_overnight_level_touch_emits_first_touch_each_level_and_both_arms():
    from event_generators import OvernightLevelTouchV1
    d = datetime(2024, 3, 5).date()
    g = OvernightLevelTouchV1(tick_size=0.1, atr_period=14)
    for row in overnight_bars(d):
        assert g.on_bar(row) == []
    # first RTH 30m bar touches the overnight high only
    events = g.on_bar(bar(datetime(2024, 3, 5, 10, 0), 100, 111, 98, 108))
    assert len(events) == 1
    ts, side, level, risk, ctx = events[0]
    assert (ts, side, level) == (datetime(2024, 3, 5, 10), -1, 110.0)
    assert risk > 0
    assert ctx["level_kind"] == "overnight_high"
    assert ctx["overnight_range_points"] == 20.0
    assert ctx["overnight_range_atr"] > 0
    assert ctx["touch_time_et"] == "10:00"
    assert ctx["resolve_both_directions"] is True
    # same level cannot fire twice; low can still fire once later
    assert g.on_bar(bar(datetime(2024, 3, 5, 10, 30), 108, 112, 96, 100)) == []
    events = g.on_bar(bar(datetime(2024, 3, 5, 11, 0), 100, 104, 89, 92))
    assert len(events) == 1 and events[0][1] == 1
    assert g.on_bar(bar(datetime(2024, 3, 5, 11, 30), 92, 102, 88, 95)) == []


def test_overnight_generator_fails_closed_on_gap_and_rollover():
    from event_generators import OvernightLevelTouchV1
    d = datetime(2024, 3, 5).date()
    rows = overnight_bars(d)
    g = OvernightLevelTouchV1(0.1)
    for row in rows[:10] + rows[11:]:
        g.on_bar(row)
    assert g.on_bar(bar(datetime(2024, 3, 5, 10), 100, 120, 80, 100)) == []
    g = OvernightLevelTouchV1(0.1)
    for row in rows[:20]:
        g.on_bar(row)
    g.on_rollover(datetime(2024, 3, 5, 4), "GCG24", "GCJ24")
    for row in rows[20:]:
        g.on_bar(row)
    assert g.on_bar(bar(datetime(2024, 3, 5, 10), 100, 120, 80, 100)) == []


def test_gc_market_spec_and_30m_contract():
    from market_specs import MARKET_SPECS
    gc = MARKET_SPECS["GC"]
    assert gc["tick_size"] == 0.10
    assert gc["point_value"] == 100.0
    assert gc["session_open_et"] == "18:00"
    assert gc["session_close_et"] == "17:00"
    assert gc["contract_months"] == (2, 4, 6, 8, 10, 12)
    assert gc["mapping_mode"] == "OPEN_INTEREST"
    assert gc["normalization_mode"] == "RAW"
    assert gc["event_bar_minutes"] == 30


def test_campaign2_context_and_ft_payloads_roundtrip_exactly():
    from event_generators import (decode_campaign2_context,
                                  decode_campaign2_ft,
                                  pack_campaign2_context,
                                  pack_campaign2_ft)
    context = {"overnight_range_points": 20.0,
               "overnight_range_atr": 1.375,
               "touch_minute_et": 615,
               "level_kind": "overnight_low"}
    packed_context = pack_campaign2_context(context, tick_size=0.1)
    assert packed_context < 2 ** 53
    assert decode_campaign2_context(packed_context, 0.1) == context
    ft32 = 0xA5A55A5A
    for arm in ("reversal", "continuation"):
        for level in ("overnight_high", "overnight_low"):
            packed = pack_campaign2_ft(ft32, arm, level)
            assert packed < 2 ** 53
            assert decode_campaign2_ft(packed) == {
                "ft32": ft32, "arm": arm, "level_kind": level}


def test_real_engine_30m_handler_emits_both_direction_arms_with_context():
    from event_generators import OvernightLevelTouchV1
    from test_scifvg_local import make_alg
    d = datetime(2024, 3, 5).date()
    a = make_alg()
    a.cfg.update({"variant": "events_only",
                  "event_generator": "overnight_level_touch_v1",
                  "event_horizons": [30, 60, 120, 240]})
    a.camp_start = d
    a.event_generator = OvernightLevelTouchV1(0.1)
    a._abs_event_bar = -1

    class C:
        pass

    def feed(row):
        c = C()
        c.end_time = row["et"]
        c.open, c.high, c.low, c.close = (row[k] for k in
                                          ("open", "high", "low", "close"))
        a._on_30m_consolidated(c)

    for row in overnight_bars(d):
        feed(row)
    feed(bar(datetime(2024, 3, 5, 10), 100, 111, 98, 108))
    assert len(a._ev_candidates) == 2
    assert {e["arm"] for e in a._ev_candidates} == {"reversal", "continuation"}
    assert all(e["overnight_range_points"] == 20.0 for e in a._ev_candidates)
    feed(bar(datetime(2024, 3, 5, 10, 30), 108, 109, 101, 105))
    results = [r for r in a._ev_results if r["h_min"] == 30]
    assert len(results) == 2
    assert {r["arm"] for r in results} == {"reversal", "continuation"}
    assert all(r["touch_time_et"] == "10:00" for r in results)


def test_real_export_packs_both_arms_and_context_without_new_series_names():
    from event_generators import decode_campaign2_context, decode_campaign2_ft
    from test_scifvg_local import make_alg
    a = make_alg()
    a.cfg.update({"variant": "events_only",
                  "event_generator": "overnight_level_touch_v1"})
    a.tick = 0.1
    base = {"event_id": "e1", "last_reclaim_et": "2024-03-05 12:00:00",
            "event_et": "2024-03-05 10:00:00", "bias_aligned": True,
            "side": -1, "date": "2024-03-05", "session_type": 0,
            "h_min": 120, "ret_r": 0.1, "risk_dist": 5.0,
            "mfe_r": 0.5, "mae_r": -0.2,
            "ft": {f"T{t:g}S{s:g}": 1 for t in (0.5, 1.0, 1.5, 2.0)
                   for s in (0.5, 1.0, 1.5, 2.0)},
            "event_predicate_mask": 1, "generator": "overnight_level_touch_v1",
            "reference_level": 110.0, "level_kind": "overnight_high",
            "session_date": "2024-03-05", "overnight_range_points": 20.0,
            "overnight_range_atr": 1.375, "touch_time_et": "10:00",
            "touch_minute_et": 600, "roll_generation": 0}
    a._ev_results = [dict(base, arm="reversal"),
                     dict(base, arm="continuation", bias_aligned=False,
                          side=1)]
    a._export_charts()
    ft_values = [int(p.y) for p in a.charts["E19B-FT"].series["a"].values]
    assert len(ft_values) == 2
    assert {decode_campaign2_ft(v)["arm"] for v in ft_values} == {
        "reversal", "continuation"}
    ctx_values = a.charts["C2-context"].series["a"].values
    assert len(ctx_values) == 1
    assert decode_campaign2_context(int(ctx_values[0].y), 0.1) == {
        "overnight_range_points": 20.0, "overnight_range_atr": 1.375,
        "touch_minute_et": 600, "level_kind": "overnight_high"}


def test_three_outcome_rule_and_feasibility_simulation():
    from campaign2_analysis import (classify_primary, simulate_label_feasibility,
                                    OPERABILITY_SCENARIOS)
    assert classify_primary(0.30, 0.25, 0.35) == "POSITIVE"
    assert classify_primary(-0.30, -0.35, -0.25) == "POSITIVE"  # continuation
    assert classify_primary(0.05, -0.05, 0.15) == "NULL"
    assert classify_primary(0.18, 0.05, 0.31) == "INCONCLUSIVE"
    assert classify_primary(0.21, 0.19, 0.23) == "INCONCLUSIVE"  # touches θ
    report = simulate_label_feasibility(n=800, sessions=400, reps=50,
                                        seed="C2-feasibility-v1")
    assert report["sessions"] < report["n"]
    assert set(report["scenarios"]) == set(OPERABILITY_SCENARIOS) | {
        "near_threshold_positive"}
    assert all(s["fire_rate"] >= 0 for s in report["scenarios"].values())
    assert report["all_scenarios_pass"]


def test_atr_floor_rejects_quiet_regime_and_entry_style_moves_only_px():
    from event_generators import OvernightLevelTouchV1
    d = datetime(2024, 3, 5).date()
    # tick 3.0 -> floor 30 points, far above the ~17.5 ATR of these bars
    g = OvernightLevelTouchV1(tick_size=3.0, atr_period=14)
    for row in overnight_bars(d):
        assert g.on_bar(row) == []
    assert g.on_bar(bar(datetime(2024, 3, 5, 10), 100, 111, 98, 108)) == []
    assert g.atr_floor_rejects == 1
    # level vs touch_close style differ ONLY in entry px; level/risk/timing
    # are identical, so the sensitivity isolates the entry convention
    base = {}
    for style in ("level", "touch_close"):
        h = OvernightLevelTouchV1(tick_size=0.1, entry_style=style)
        for row in overnight_bars(d):
            h.on_bar(row)
        events = h.on_bar(bar(datetime(2024, 3, 5, 10), 100, 111, 98, 108))
        ts, side, level, risk, ctx = events[0]
        base[style] = {"entry": ctx["entry_px"], "level": level,
                       "risk": risk, "close": ctx["touch_bar_close"]}
    assert base["level"]["entry"] == base["level"]["level"] == 110.0
    assert base["touch_close"]["entry"] == base["touch_close"]["close"] == 108.0
    assert base["level"]["level"] == base["touch_close"]["level"]
    assert base["level"]["risk"] == base["touch_close"]["risk"]


def run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)


if __name__ == "__main__":
    run_all()
