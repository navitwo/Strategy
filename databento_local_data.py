"""Local Databento -> Campaign-2 30-minute bar pipeline (guards a/b/c live here).

Provenance: data/databento/*.zip purchased 2026-09-04 ($38.04, continuous
NQ.n.0 + GC.n.0, 2010-06-07 -> 2026-09-04 exclusive; see DATABENTO_BUDGET.md
and manifest.json). Prices are UNADJUSTED underlying-contract prices, i.e.
the RAW-normalization equivalent; the continuous symbol selects, per
interval, the current front-month contract (first-party open-interest
mapping -- Campaign 1's DataMappingMode.OPEN_INTEREST + RAW analogue).

Guards (all mandatory, C2-ONLT-v1 2026-09-04):
  (a) DateGate: reading bars whose session date is after DEV_END (2024-12-31)
      physically refuses unless VALIDATION_UNLOCK -- a COMMITTED constant,
      currently False -- is True. Validation/holdout stay locked even though
      the files on disk contain them.
  (b) Rolls are embedded in the stream: the underlying symbol changes while
      the continuous symbol does not. detect_rolls() surfaces every change;
      consumers must apply Campaign 1's rule (a mapping event resets ATR and
      invalidates any partial overnight) via OvernightLevelTouchV1.on_rollover.
  (c) Bars are aggregated on ET wall-clock half-hours; the completed-bar row
      shape matches what scifvg_main._on_30m_consolidated feeds the frozen
      generator: {open, high, low, close, et(datetime, END time)} -- plus
      volume, trade_date, and underlying symbol for roll handling.

stdlib + pandas (pandas is dev-machine only, NEVER imported by the hosted
bundle). No numpy semantics the frozen generator does not already accept.
"""
import json
import os
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
UTC = timezone.utc

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO_ROOT, "data", "databento")
OHLCV_FILE = os.path.join(DATA_DIR, "glbx-mdp3-ohlcv-1m.zip")
DEFINITION_FILE = os.path.join(DATA_DIR, "glbx-mdp3-definition.zip")

# ---- guard (a): the date gate ------------------------------------------------
DEV_END = date(2024, 12, 31)          # last session date readable without flag
VALIDATION_UNLOCK = False             # flip requires a committed change


class DateGateError(RuntimeError):
    """Refusal to read validation/holdout dates without the committed flag."""


def check_session_dates(session_dates, unlocked=False):
    """Hard gate on a set/iterable of session dates (datetime.date).

    ``unlocked`` must be supplied BY THE CALLER as the literal value of the
    committed VALIDATION_UNLOCK constant; the default keeps every ordinary
    call site locked. Raises before any bar is returned.
    """
    if unlocked:
        return
    bad = sorted({d for d in session_dates if d > DEV_END})
    if bad:
        raise DateGateError(
            f"refusing to read {len(bad)} session date(s) past "
            f"{DEV_END.isoformat()} (e.g. {bad[0].isoformat()}) with "
            "VALIDATION_UNLOCK False; validation and holdout remain locked")


# ---- DBN decoding -------------------------------------------------------------

def _is_zip(path):
    with open(path, "rb") as fh:
        return fh.read(4) == b"PK\x03\x04"


def iter_dbn_frames(path, schema, day_filter=None):
    """Yield (member_day_utc_date, DataFrame) over a purchased DBN file.

    Handles BOTH shapes Databento ships: a single .dbn file, and a ZIP
    container of per-UTC-day .dbn.zst members (what multi-file batch jobs
    deliver regardless of the compression flag). Members are decoded one
    day at a time -- never the whole stream into memory at once.

    The frame is indexed on ts_event; the symbol column is the CONTINUOUS
    request symbol (GC.n.0 / NQ.n.0) and instrument_id identifies the
    underlying contract actually mapped at each timestamp (the embedded
    roll). UTC-day members straddle ET days: an evening of ET day D lives
    in UTC member D and D+1, so callers filtering by ET date must widen
    the member filter (see dbn_minute_rows).
    """
    import databento
    if _is_zip(path):
        with zipfile.ZipFile(path) as zf:
            members = sorted(n for n in zf.namelist()
                             if n.endswith(".dbn.zst"))
            for name in members:
                day = datetime.strptime(name.split("-")[2].split(".")[0],
                                        "%Y%m%d").date()
                if day_filter is not None and day not in day_filter:
                    continue
                with zf.open(name) as fh:
                    raw = fh.read()
                store = databento.DBNStore.from_bytes(raw)
                df = store.to_df(schema=schema, map_symbols=True)
                if len(df):
                    yield day, df
    else:
        store = databento.read_dbn(path)
        df = store.to_df(schema=schema, map_symbols=True)
        df = df.assign(_ts=df.index.tz_localize(None).normalize().dt.date
                       if getattr(df.index, "tz", None)
                       else df.index.normalize().date)
        for day, sub in df.groupby("_ts"):
            yield day, sub.drop(columns="_ts")


def load_instrument_map(path=DEFINITION_FILE):
    """{(instrument_id): [(d0, d1, future_symbol)]} from the purchased
    definition schema, cached to a sidecar JSON.

    instrument_ids are REUSED across instruments over the years, so
    lookups MUST be date-aware: resolve_raw_symbol(iid, day) below.
    A definition record's first_date/last_date is its trading interval.
    """
    cache = os.path.join(DATA_DIR, "instrument_map.json")
    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as fh:
            raw = json.load(fh)
        return {int(k): [(a, b, s) for a, b, s in v] for k, v in raw.items()}
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    import databento
    by_iid = {}
    if _is_zip(path):
        with zipfile.ZipFile(path) as zf:
            members = sorted(n for n in zf.namelist()
                             if n.endswith(".dbn") or n.endswith(".dbn.zst"))
            # every definition record carries its OWN first/last_date, and
            # front-relevant contracts trade for months; sampling weekly
            # members observes them all without ~5,000-file decode cost.
            # (Short-lived non-front instruments may be missed by design —
            # resolve_raw_symbol then fails LOUDLY at the call site.)
            sampled = members[::21] or members
            for name in sampled:
                with zf.open(name) as fh:
                    raw = fh.read()
                df = databento.DBNStore.from_bytes(raw).to_df(
                    schema="definition")
                cols = ("instrument_id", "future_symbol", "first_date",
                        "last_date")
                for iid, fut, d0, d1 in zip(*(df[c].values for c in cols)):
                    rec = (str(d0)[:10], str(d1)[:10], str(fut))
                    by_iid.setdefault(int(iid), set()).add(rec)
    else:
        df = databento.read_dbn(path).to_df(schema="definition")
        for iid, fut, d0, d1 in zip(df["instrument_id"].values,
                                    df["future_symbol"].values,
                                    df["first_date"].values,
                                    df["last_date"].values):
            by_iid.setdefault(int(iid), set()).add(
                (str(d0)[:10], str(d1)[:10], str(fut)))
    out = {iid: sorted(v) for iid, v in by_iid.items()}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump({str(k): v for k, v in out.items()}, fh)
    return out


def resolve_raw_symbol(instrument_map, instrument_id, on_date):
    """Raw future symbol (e.g. 'GCZ13') for one instrument_id at a date."""
    for d0, d1, sym in instrument_map.get(instrument_id, []):
        if d0 <= on_date.isoformat() <= d1:
            return sym
    raise KeyError(
        f"instrument {instrument_id} has no definition interval covering "
        f"{on_date.isoformat()}")


def dbn_minute_rows(path, market, day_filter, instrument_map=None,
                    unlocked=False):
    """Minute rows for one market over UTC-day members around the requested
    ET days. Returns sorted {ts_event_ns, instrument_id, cont_symbol,
    symbol, open, high, low, close, volume} dicts.

    Guard (a) is enforced HERE too, not only in session_rows: any member
    past DEV_END can only belong to a post-gate session (verified
    arithmetic), so requesting one raises unless ``unlocked`` is True. No
    public primitive can read validation/holdout days without the flag.

    ``instrument_map``: the date-aware map from load_instrument_map();
    ``symbol`` then carries the RAW future name (GCZ13). Without it,
    symbol falls back to the instrument_id string (roll detection and bar
    OHLC unaffected; the raw name only matters for QC joins).
    """
    past_gate = sorted({d for d in day_filter if d > DEV_END})
    if past_gate and not unlocked:
        raise DateGateError(
            f"refusing to decode {len(past_gate)} UTC member(s) past "
            f"{DEV_END.isoformat()} (e.g. {past_gate[0].isoformat()}) "
            "without the validation unlock")
    rows = []
    for day, df in iter_dbn_frames(path, "ohlcv-1m", day_filter=day_filter):
        index = df.index
        for ts, cont_symbol, iid, o, h, l, c, v in zip(
                index.values, df["symbol"].values,
                df["instrument_id"].values,
                df["open"].values, df["high"].values, df["low"].values,
                df["close"].values, df["volume"].values):
            cont_symbol = str(cont_symbol)
            if market_root(cont_symbol) != market:
                continue
            # pretty_ts=True yields tz-aware UTC Timestamps; .value is
            # epoch ns. If tz were stripped it is already UTC ns.
            ts_ns = int(getattr(ts, "value", ts))
            raw = None
            if instrument_map is not None:
                try:
                    raw = resolve_raw_symbol(instrument_map, int(iid),
                                             ts_to_et(ts_ns).date())
                except KeyError:
                    raw = None
            rows.append({"ts_event_ns": ts_ns,
                         "instrument_id": int(iid),
                         "cont_symbol": cont_symbol,
                         "symbol": raw if raw is not None else str(int(iid)),
                         "open": float(o), "high": float(h),
                         "low": float(l), "close": float(c),
                         "volume": int(v)})
    rows.sort(key=lambda r: r["ts_event_ns"])
    return rows


# Futures month codes (standard CME cycle: F G H J K M N Q U V X Z; there
# is no S/I/L — September is U, November X, December Z)
_MONTH_CODES = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
                "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}


def raw_symbol_to_yyyymm(symbol, ref_year, ref_month):
    """'GCZ13' / 'GCZ3' style -> '201312'.

    Both 1- and 2-digit years appear in raw futures symbology; a short year
    is resolved against the record's own (ref_year, ref_month): the delivery
    is the FIRST month matching the year ending at or after the reference
    month. Front-month series never carry an expired delivery, so this is
    exact for this dataset.
    """
    m = re.match(r"^[A-Za-z]+([FGHJKMNQUVXZ])(\d{1,2})$", symbol)
    if not m:
        raise ValueError(f"unrecognized raw symbol {symbol!r}")
    month = _MONTH_CODES[m.group(1)]
    digits = m.group(2)
    if len(digits) == 2:
        year = 2000 + int(digits)
    else:
        digit = int(digits)
        year = ref_year
        if year % 10 != digit or (year == ref_year and month < ref_month):
            year += 1
            while year % 10 != digit:
                year += 1
    return f"{year:04d}{month:02d}"


def market_root(symbol):
    """Map a raw contract symbol (NQZ24, GCZ24, GCG25...) to its market root."""
    m = re.match(r"^(NQ|GC|ES|YM|RTY)", symbol)
    if not m:
        raise ValueError(f"unrecognized contract symbol {symbol!r}")
    return m.group(1)


def ts_to_et(ts_ns):
    """Epoch-ns UTC -> NAIVE ET wall-clock datetime.

    The frozen generator contract (hosted consolidated.end_time and every
    campaign ledger) uses naive ET wall-clock datetimes; keeping tz here
    would break its `et != expected` contiguity comparisons and change no
    semantics otherwise.
    """
    return datetime.fromtimestamp(ts_ns / 1e9, tz=UTC).astimezone(
        ET).replace(tzinfo=None)


# ---- guard (b)+(c): roll-aware 30m aggregation -------------------------------

def _floor_et_to_half_hour(dt_et):
    m = dt_et.hour * 60 + dt_et.minute
    slot = (m // 30) * 30
    return dt_et.replace(hour=slot // 60, minute=slot % 60, second=0,
                         microsecond=0)


def build_bars_30m(minute_rows, drop_zero_volume=True):
    """Aggregate {ts_event_ns, symbol, o,h,l,c,v} minute rows into completed
    30-minute ET wall-clock bars. Bars carry the END time as ``et`` (Lean
    convention) and the underlying symbol that produced them.

    Lean's DefaultDataProvider emits a minute bar only for minutes with
    trades, so Databento's synthetic zero-volume minutes (volume==0,
    openPriceType synthetic) are dropped before aggregation by default --
    without that, the local path would feed the generator bars the hosted
    path never had.

    Bucketing is by half-hour slot ONLY: one contract's minutes per slot,
    and a slot whose minutes span two contracts (a roll landing mid-half-
    hour) is recorded as a MIXED bar, excluded from the bar stream, and its
    presence is returned in ``mixed``. A mixed bar makes the generator's
    contiguous-endpoint check fail closed, which is exactly how the hosted
    path treats the interval around a mapping event.

    minute_rows must be sorted by ts_event_ns. Returns (bars, mixed_slots).
    """
    bars = []
    mixed = []
    cur = None
    cur_symbols = set()
    for r in minute_rows:
        if drop_zero_volume and r["volume"] <= 0:
            continue
        start_et = ts_to_et(r["ts_event_ns"])
        slot = _floor_et_to_half_hour(start_et)
        end_et = slot + timedelta(minutes=30)
        if cur is not None and cur["_slot"] == slot:
            cur_symbols.add(r["symbol"])
            cur["high"] = max(cur["high"], r["high"])
            cur["low"] = min(cur["low"], r["low"])
            cur["close"] = r["close"]
            cur["volume"] += r["volume"]
            continue
        if cur is not None:
            if len(cur_symbols) > 1:
                mixed.append(cur["et"])  # roll landed inside this slot
            else:
                bars.append(cur)
        cur_symbols = {r["symbol"]}
        cur = {"_slot": slot, "open": r["open"], "high": r["high"],
               "low": r["low"], "close": r["close"], "volume": r["volume"],
               "et": end_et, "symbol": r["symbol"]}
    if cur is not None:
        if len(cur_symbols) > 1:
            mixed.append(cur["et"])
        else:
            bars.append(cur)
    for b in bars:
        b.pop("_slot", None)
        b["trade_date"] = trade_date_of(b["et"])
    return bars, mixed


def trade_date_of(et_dt):
    """Generator's convention: bars at/after 18:00 ET belong to next date."""
    d = et_dt.date()
    return d + timedelta(days=1) if et_dt.hour >= 18 else d


def detect_rolls(minute_rows):
    """Guard (b), stream side: the roll is embedded, not announced. A
    change of the underlying instrument within one continuous stream is a
    mapping event.

    Returns [{ts_event_ns, et, trade_date, old_instrument_id,
    old_symbol, new_instrument_id, new_symbol}] in stream order.
    Consumers must call on_rollover(...) at the FIRST completed bar whose
    minutes include the new instrument, BEFORE feeding that bar.
    """
    rolls = []
    prev = None
    for r in minute_rows:
        if prev is not None and r["instrument_id"] != prev["instrument_id"]:
            et = ts_to_et(r["ts_event_ns"])
            rolls.append({
                "ts_event_ns": r["ts_event_ns"], "et": et,
                "trade_date": trade_date_of(et),
                "old_instrument_id": prev["instrument_id"],
                "new_instrument_id": r["instrument_id"],
                "old_symbol": prev["symbol"], "new_symbol": r["symbol"]})
        prev = r
    return rolls


def build_mapping_table(minute_rows):
    """Guard (b), definition-side view: {continuous_symbol:
    {trade_date: instrument_id}} plus roll sessions, built from the
    stream's mapping records PER CONTINUOUS SYMBOL.

    A roll landing at/after 18:00 ET sits INSIDE the next session's
    overnight (detected: NQ 2020-03-18 20:00 ET). Within one continuous
    symbol one instrument change per trade date is legitimate and is
    recorded (that session's overnight is invalidated by the mixed bar
    regardless); a second distinct change inside one session is a data
    defect and raises. Returns (tables, rolls) where rolls is a list of
    {cont_symbol, trade_date, old_instrument_id, new_instrument_id}.
    """
    tables = {}   # cont -> {trade_date: instrument_id that OPENED session}
    observed = {}  # (cont, trade_date) -> set of instruments seen that day
    rolls = []
    for r in minute_rows:
        cont = r.get("cont_symbol", "cont")
        td = trade_date_of(ts_to_et(r["ts_event_ns"]))
        table = tables.setdefault(cont, {})
        obs = observed.setdefault((cont, td), set())
        if td not in table:
            table[td] = r["instrument_id"]
        before = len(obs)
        obs.add(r["instrument_id"])
        if before == 1 and len(obs) == 2:
            # the session just acquired its SECOND instrument: exactly one
            # transition event, at first sight of the new one
            rolls.append({"cont_symbol": cont, "trade_date": td,
                          "old_instrument_id": table[td],
                          "new_instrument_id": r["instrument_id"]})
        elif len(obs) > 2:
            raise AssertionError(
                f"{cont}: multiple instruments in session {td}: "
                f"{sorted(obs)} — beyond a single roll; inspect stream")
    return tables, rolls


def mapping_roll_sessions(minute_rows):
    """Roll sessions, definition-view. Cross-validates detect_rolls:
    every stream roll's trade_date must appear here, and vice versa."""
    _tables, rolls = build_mapping_table(minute_rows)
    return rolls


def bars_to_generator_rows(bars):
    """Rows exactly shaped for OvernightLevelTouchV1.on_bar / the hosted
    _on_30m_consolidated aggregation dict."""
    return [{"open": b["open"], "high": b["high"], "low": b["low"],
             "close": b["close"], "et": b["et"], "symbol": b["symbol"]}
            for b in bars]


# ---- loading purchased data (with guard applied at the edge) -----------------

def _member_days_from_zip(path):
    with zipfile.ZipFile(path) as zf:
        days = set()
        for name in zf.namelist():
            if name.endswith(".dbn.zst"):
                days.add(datetime.strptime(
                    name.split("-")[2].split(".")[0], "%Y%m%d").date())
    return days


def available_days(path=OHLCV_FILE):
    """Every dataset day physically on disk (from the container index; no
    decode). Validation and holdout days ARE on disk — the gate is what
    keeps them unread without the committed flag."""
    if _is_zip(path):
        return _member_days_from_zip(path)
    raise NotImplementedError("single-file DBN: derive days from metadata")


def widen_member_days(et_days):
    """UTC members {D-1, D} for session (trade) dates around D.

    Verified empirically on real data: session D spans ET D-1 18:00 →
    D 17:59 = UTC ~D-1 22:00 → D 22:59, so its rows live ONLY in members
    {D-1, D}; member D+1 holds the NEXT session's evening and must not be
    pulled (that over-inclusion made a locked request for the final dev
    session falsely touch a post-gate member). ET-CALENDAR filtering (not
    used by the trade-date pipeline) would additionally need D+1.
    """
    days = set(et_days)
    return {d - timedelta(days=1) for d in days} | days


def session_rows(market, session_days=None, unlocked=False,
                 instrument_map=None, path=OHLCV_FILE):
    """THE research-facing data accessor: minute rows for one market keyed
    on SESSION (trade) date, with guard (a) enforced by construction.

      - session_days=None (the default): only members <= DEV_END are ever
        decoded and only rows with trade_date <= DEV_END returned —
        validation/holdout never enter memory.
      - explicit session_days: any date past DEV_END raises DateGateError
        unless the caller passes unlocked=True (the value of the committed
        VALIDATION_UNLOCK constant).

    dbn_minute_rows below is the raw primitive and stays private to this
    module's gated paths and the permanent tests; research code must go
    through session_rows / load_purchased_bars.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} missing; purchase not on disk (data/ is git-"
            "ignored by design)")
    avail = available_days(path)
    if session_days is None:
        member_filter = {d for d in avail if d <= DEV_END}
    else:
        session_days = set(session_days)
        check_session_dates(session_days, unlocked=unlocked)
        member_filter = widen_member_days(session_days) & avail
        missing = {d for d in session_days
                   if not ({d - timedelta(days=1), d} & avail)}
        if missing:
            raise FileNotFoundError(
                f"requested session days not on disk: "
                f"{sorted(str(m) for m in missing)[:4]}")
    rows = dbn_minute_rows(path, market, member_filter,
                           instrument_map=instrument_map,
                           unlocked=unlocked)
    if session_days is None:
        return [r for r in rows
                if trade_date_of(ts_to_et(r["ts_event_ns"])) <= DEV_END]
    return [r for r in rows
            if trade_date_of(ts_to_et(r["ts_event_ns"])) in session_days]


def load_purchased_bars(markets=("NQ", "GC"), days=None, unlocked=False,
                        instrument_map=None):
    """Gated session rows -> per-market sorted minute rows -> 30m bars.

    Guard (a) applies through session_rows for BOTH mechanisms (default
    truncation + explicit refusal); see its docstring.
    """
    out = {}
    for market in markets:
        rows = session_rows(market, session_days=days, unlocked=unlocked,
                            instrument_map=instrument_map)
        bars, mixed = build_bars_30m(rows)
        out[market] = {"bars": bars, "minute_rows": rows,
                       "rolls": detect_rolls(rows), "mixed_slots": mixed}
    return out


# ---- QuantConnect bundle side of guard (c) -----------------------------------

QC_FUTURE_DIR = os.path.join(REPO_ROOT, "data", "future")


def qc_minute_bars(venue, ticker, yyyymmdd, kinds=("trade",),
                   expiry_filter=None):
    """QC Lean minute bars from the bundled zip as sorted minute-row dicts
    shaped like the DBN rows ({ts_event_ns, symbol, open, high, low, close,
    volume}).

    ``expiry_filter``: set of yyyymm strings — only CSVs whose expiry-month
    tag is in the set are read. Lean's DefaultDataProvider emits a minute
    ONLY for minutes with trades, and its zips contain every listed expiry:
    reconciliation must restrict to the DBN-mapped contract.
    """
    rows = []
    for kind in kinds:
        path = os.path.join(QC_FUTURE_DIR, venue, "minute", ticker,
                            f"{yyyymmdd}_{kind}.zip")
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        day = datetime.strptime(yyyymmdd, "%Y%m%d").date()
        with zipfile.ZipFile(path) as zf:
            names = sorted(n for n in zf.namelist() if f"_{kind}_" in n)
            for name in names:
                expiry_tag = name.rsplit("_", 1)[-1].split(".")[0]
                if expiry_filter is not None \
                        and expiry_tag not in expiry_filter:
                    continue
                for line in zf.open(name):
                    parts = line.decode().strip().split(",")
                    if len(parts) < 6:
                        continue
                    ms, o, h, l, c, v = (parts[0], float(parts[1]),
                                         float(parts[2]), float(parts[3]),
                                         float(parts[4]), int(parts[5]))
                    t_utc = datetime(day.year, day.month, day.day,
                                     tzinfo=UTC) + timedelta(
                        milliseconds=int(ms))
                    rows.append({
                        "ts_event_ns": int(t_utc.timestamp() * 1e9),
                        "symbol": expiry_tag,
                        "open": o, "high": h, "low": l, "close": c,
                        "volume": v})
    rows.sort(key=lambda r: r["ts_event_ns"])
    return rows
