"""Pure configuration constants shared by the hosted engine and local tests."""

FT_CELLS = [(f"T{t:g}S{s:g}", t, s) for t in (.5, 1, 1.5, 2)
            for s in (.5, 1, 1.5, 2)]

CONFIG_KEYS = (
    "instrument", "start_date", "end_date", "run_segment",
    "sweep_min_ticks", "sweep_max_ticks", "reclaim_bars",
    "cisd_max_bars", "inv_max_bars", "retest_max_bars",
    "fvg_min_ticks", "fvg_max_age_bars", "stop_buffer_ticks",
    "target_r", "risk_usd", "max_contracts", "slippage_ticks",
    "commission_per_side", "window_start_et", "window_end_et",
    "invert_on_cisd_bar", "entry_location", "pivot_lookback", "pivot_right",
    "max_attempts_per_day", "stop_mode", "min_stop_ticks", "floor_atr_frac",
    "entry_mode", "random_entry_prob", "variant", "event_horizons",
    "depth_min_bps", "depth_max_bps", "stop_buffer_bps", "counter_bias_arm",
    "event_predicates")

CONFIG_DEFAULTS = {
    "instrument": "MNQ", "start_date": "2023-01-03", "end_date": "2025-04-30",
    "run_segment": "dev", "sweep_min_ticks": 4, "sweep_max_ticks": 96,
    "reclaim_bars": 3, "cisd_max_bars": 12, "inv_max_bars": 12,
    "retest_max_bars": 24, "fvg_min_ticks": 4, "fvg_max_age_bars": 60,
    "stop_buffer_ticks": 4, "target_r": 2.0, "risk_usd": 100.0,
    "max_contracts": 10, "slippage_ticks": 1, "commission_per_side": 0.50,
    "window_start_et": "09:30", "window_end_et": "12:00",
    "invert_on_cisd_bar": 0, "entry_location": "proximal",
    "pivot_lookback": 3, "pivot_right": 3, "max_attempts_per_day": 1,
    "stop_mode": "sweep", "entry_mode": "signal", "random_entry_prob": 0.02,
    "variant": "candidate", "event_predicates": "sweep_reclaim_v1",
    "event_horizons": [30, 60, 120, 240], "depth_min_bps": 0.0,
    "depth_max_bps": 0.0, "stop_buffer_bps": 0.0,
    "min_stop_ticks": 0.0, "floor_atr_frac": 0.0,
}


def canonical_identity_config(cfg):
    identity = dict(cfg)
    if (identity.get("event_predicates") == "sweep_reclaim_v1"
            and identity.get("variant") != "discovery_only"):
        identity.pop("event_predicates")
    return identity


FUNNEL_KEYS = [
    "sessions", "no_prior_levels", "no_bias", "attempts_used",
    "excursion_depth_kills", "L_floor_rejects", "S_floor_rejects",
    "rollover_no_mark", "L_attempts", "L_depth_rejects", "L_no_reclaim",
    "L_sweep_ok", "L_cisd_ok", "L_cisd_timeout", "L_inv_ok",
    "L_inv_timeout", "L_submits", "L_fills", "L_size_skips",
    "L_cancel_expiry", "L_cancel_invalid", "L_cancel_bias",
    "L_cancel_window", "L_cancel_other", "S_attempts", "S_depth_rejects",
    "S_no_reclaim", "S_sweep_ok", "S_cisd_ok", "S_cisd_timeout",
    "S_inv_ok", "S_inv_timeout", "S_submits", "S_fills", "S_size_skips",
    "S_cancel_expiry", "S_cancel_invalid", "S_cancel_bias",
    "S_cancel_window", "S_cancel_other", "rollovers", "oco_races",
    "forced_flattens", "end_flattens", "eod_flattens", "flatten_fills",
    "untracked_fills", "oco_void_legs", "anomalous_exit_events",
    "cycles_opened", "atomic_exits",
]
