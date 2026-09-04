# Campaign 2 — Overnight-Level Bare-Touch Event Study

**Status:** FROZEN PRE-REGISTRATION — NO MARKET DATA PULLED, NO BACKTEST, NO OPTIMIZATION  
**Protocol:** `C2-ONLT-v1`  
**Frozen:** 2026-09-01  
**Validation/holdout:** LOCKED

## 1. Question and prior

Does the first regular-session bare touch of the completed full-session overnight high or low contain an economically meaningful directional effect, and is the effect reversal or continuation?

The prior is deliberately unfavorable for NQ: it tests a liquidity-reference level closely related to the sweep/reclaim family already shown by FT32E to be a coin flip across its ambiguity interval. GC is the genuinely untested replication leg. Removing the reclaim requirement creates a new bare-touch population; it does not rehabilitate Campaign 1.

## 2. Frozen population

- Markets: **NQ** and **GC** only; never MNQ/MGC.
- Common development interval: **2010-06-07 through 2024-12-31**.
- Validation: **2025-01-01 through 2025-12-31**, locked and unread.
- Holdout: **2026-01-01 onward**, locked and unread.
- Source bars: one-minute trades consolidated natively to completed **30-minute ET bars**.
- Continuous futures: current mapped contract, `OPEN_INTEREST` mapping, `RAW` normalization. GC delivery months are Feb/Apr/Jun/Aug/Oct/Dec. A mapping event resets ATR and invalidates the partial overnight; no event can be published until a later complete overnight is observed.
- Session: 18:00 ET previous calendar day through 17:00 ET trade date, with 17:00–18:00 maintenance.

A complete overnight is exactly 31 contiguous completed 30-minute endpoints from 18:30 ET through 09:30 ET. A gap, partial lifecycle, mid-session start, or rollover fails closed.

## 3. Frozen event generator

`EventGenerator` emits exactly:

`(timestamp, side, reference_level, risk_dist, context)`

`overnight_level_touch_v1`:

1. Compute the high and low over the complete overnight, 18:00 previous day → 09:30 trade date.
2. Inspect completed RTH 30-minute bars ending 10:00, 10:30, 11:00, 11:30, 12:00, and 12:30 ET.
3. Emit the first bare touch of each level, at most one high event and one low event per session. No reclaim, bias, CISD, FVG, IFVG, depth, or other gate is permitted.
4. High touch is signed short toward the reference; low touch is signed long toward it.
5. Resolve both the signed **reversal** arm and the exact opposite **continuation** arm for every physical event. They share one `event_id`; arm and horizon are subkeys.
6. `risk_dist` is ex-ante ATR(14) of completed 30-minute bars, excluding the touch bar. Entry/reference price is the overnight level. The touch bar is excluded from post-event MFE/MAE and first-touch resolution to prevent pre-touch leakage.

The frozen `generator_v1` compatibility gate must reconcile the committed E19B-R ledgers exactly: NQ 388, ES 186, YM 376, RTY 171; same `chart_x`, 16 codes, and `packed_uint32` for all 1,121 rows. Failure blocks Campaign 2.

## 4. Outcomes and transport

Reuse the no-order downstream event-study layer:

- signed forward R at 30/60/120/240 minutes;
- MFE/MAE;
- 16 target/stop cells T{0.5,1,1.5,2} × S{0.5,1,1.5,2};
- pessimistic stop-first primary and optimistic target-first sensitivity for same-bar ambiguity;
- float64-exact packed FT payload, decoded ledgers, exact row reconciliation, offline screen, martingale calibration;
- same-session-date random-time control, matched on market, date, side, time-window support, and risk distance; genuine session-date clustering with a permanent `sessions < n` assertion.

New packed context per physical event:

- overnight range width in points;
- overnight range width / ex-ante ATR;
- touch time-of-day in ET.

Context is conditioning-only. No context threshold is selectable in this phase.

## 5. Sole primary

- Physical population: NQ and GC pooled with equal market weighting; each market first averages its event-level values, then the two market means are averaged. Market-specific results are mandatory descriptive replications.
- Contrast: paired `reversal payoff − continuation payoff`.
- Cell: **T2S0.5**.
- Horizon: **120 minutes**.
- Ambiguity convention: pessimistic stop-first.
- Per-arm payoff: horizon payoff winsorized to the cell's bounded range `[-0.5R, +2.0R]`; paired contrast is therefore bounded `[-2.5R, +2.5R]`.
- Inference: session-date clustered bootstrap, fixed seed, two-sided 95% interval.
- Economic threshold: **θ = 0.2R**, never widened.

Three outcomes:

- **POSITIVE:** the complete CI is above `+0.2R` (reversal) or below `−0.2R` (continuation); direction is reported.
- **NULL:** the complete CI lies inside `[-0.2R, +0.2R]`.
- **INCONCLUSIVE:** every other interval geometry.

All other cells, horizons, market splits, levels, range/ATR bins, touch-time bins, optimistic ambiguity results, raw ratios, MFE/MAE, and control contrasts are exploratory and cannot promote a strategy.

## 6. Mandatory pre-launch feasibility gate

Before any market data request, `campaign2_analysis.py` simulates a **grid** of
achievable sizes `n ∈ {200, 400, 800, 1600, 3200}` (nobody knows the achievable
sample yet: two potential events per session over ~3,650 sessions × 2 markets is
~7,300 slots, so physical events plausibly land anywhere from ~1,500 to ~6,000).
Each n uses `n/2` session-date clusters (two bounded observations per cluster),
200 fixed-seed replicates, winsorized `[−0.5R,+2.0R]` payoffs, and a clustered
bootstrap. The four operability scenarios gate the result (≥80% intended firing
at that n):

1. reversal-positive (`Δ=+0.55R`),
2. continuation-positive (`Δ=−0.55R`),
3. null-equivalent (`Δ=0R`),
4. boundary/inconclusive (`Δ=+0.2R`).

A fifth near-threshold scenario (`Δ=+0.3R`) is an MDE probe reported at every
grid point regardless of its answer (amendment 2026-09-04): whether the
0.2–0.55R band is detectable at all is the declared minimum detectable effect
record, never a stand-down trigger.

The gate output is the **minimum n at which the four operability scenarios
fire ≥80%**, frozen here as the pre-registered pass/fail number. If no grid
point passes, the study stands down before any data or cloud cost. The
simulated per-observation dispersion (`sd = 0.45R`) is also frozen in the gate
artifact; the post-data replay re-runs the identical classifier at the achieved
`n`, achieved session count, and the empirically measured clustered dispersion
and is judged against this frozen number, not re-guessed.

The test must assert `sessions < n`. This is classifier-operability evidence,
not a power claim about realized market dispersion.

### 6a. Gate executed — frozen result (2026-09-04, pre-data, zero market data)

Artifact: `c2_feasibility_grid.json` (seed `C2-feasibility-v1`, 200 reps).

- **minimum_passing_n = 200** — the frozen post-data pass/fail number.
- POSITIVE and NULL — the two informative decision labels — fired **100%** at
  every grid n including 3200.
- MDE probe: Δ=+0.3R fires POSITIVE at 97%/100%/100%/100%/100%; the
  0.2–0.55R band is declared detectable from n≥200 at the frozen dispersion.
- Boundary scenario (Δ exactly = θ) degraded with n: 93.5 / 92.0 / 86.0 /
  86.5 / **67.5%** at n=200…3200, failing the 80% floor at n=3200 only.

**Pre-data criterion correction (documented, dated, zero market data used):**
requiring the knife-edge scenario to fire INCONCLUSIVE ≥80% at every grid n
demands that the estimator be *inconsistent*: a CI that concentrates around a
true mean sitting exactly at θ must converge to a coin flip between POSITIVE
and NULL, so the INCONCLUSIVE rate at the boundary is mathematically forced
toward 0 as n grows. A criterion that cannot pass at large n is the same
class of design defect the gate exists to catch, so the replay criterion is
restated: the post-data replay requires POSITIVE and NULL (and the MDE probe
reporting) to fire ≥80% at the achieved n/sd, and requires INCONCLUSIVE
emissibility (≥80% at some grid n — satisfied at n=200), never INCONCLUSIVE
reliability at the knife edge. θ, the interval geometry, the cell, horizon,
estimator, and clustering rule are unchanged.

## 6b. ATR floor and entry-price sensitivity (pre-data amendments)

- **Minimum ATR floor (ticks):** an event is admitted only if its ex-ante
  ATR(14) over 30-minute bars is at least **10 ticks** of its market
  (NQ: 2.50 index points; GC: 1.00 point). Below that, bracket distances are so
  small that the 0.5R stop is hit almost immediately and stop-first rates
  inflate in quiet regimes. The floor is declared pre-data; the **realized ATR
  distribution per market must be published with the event ledger** so the
  floor's event-retention rate is auditable. Retention is a fail-closed
  population filter, not a selectable parameter.
- **Touch-bar-close entry sensitivity (declared variant):** the primary keeps
  entry at the overnight level (realistic for a resting limit). Because
  excluding the touch bar from resolution hides any adverse move that occurs
  after the touch and inside that bar — a real cost a live trader eats — a
  second, fully declared variant resolves the same events entering at the
  **touch bar close**. The variant is reported alongside the primary as the
  passive-limit-versus-marketable question from Campaign 1. It cannot be used
  to pick the better-looking answer: the sole primary remains level-entry.

## 7. Stop rules

- No strategy orders, strategy backtest, optimization, validation, or holdout access.
- No parameter selection from the 16-cell surface or context bins.
- No random-time control until the event ledger passes exact reconciliation.
- No rescue/strategy phase unless the sole primary is robust, economically meaningful, ambiguity-stable, and directionally supported across both markets.
- A NQ null is expected and does not invalidate a separately reported GC result; neither leg may be silently dropped.
