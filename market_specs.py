"""Frozen market/session metadata for no-order event studies."""

MARKET_SPECS = {
    "NQ": {
        "root": "NQ", "tick_size": 0.25, "point_value": 20.0,
        "session_open_et": "18:00", "session_close_et": "17:00",
        "maintenance_et": ("17:00", "18:00"),
        "contract_months": (3, 6, 9, 12),
        "mapping_mode": "OPEN_INTEREST", "normalization_mode": "RAW",
        "event_bar_minutes": 30,
    },
    "GC": {
        "root": "GC", "tick_size": 0.10, "point_value": 100.0,
        "session_open_et": "18:00", "session_close_et": "17:00",
        "maintenance_et": ("17:00", "18:00"),
        "contract_months": (2, 4, 6, 8, 10, 12),
        "mapping_mode": "OPEN_INTEREST", "normalization_mode": "RAW",
        "event_bar_minutes": 30,
    },
}


def validate_market_spec(symbol):
    spec = MARKET_SPECS[symbol]
    assert spec["session_open_et"] == "18:00"
    assert spec["session_close_et"] == "17:00"
    assert spec["mapping_mode"] == "OPEN_INTEREST"
    assert spec["normalization_mode"] == "RAW"
    assert spec["event_bar_minutes"] == 30
    assert spec["tick_size"] > 0 and spec["point_value"] > 0
    return True
