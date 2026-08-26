# PRE-REGISTRATION — E19B-R (reclaim-confirmed event study, floored)

Amendment type: **population-conformance correction only** (declared before
the run, per the E19->E19B pre-reclaim reclassification precedent). The
frozen primary from e19b-provisional — H*=120m, raw mean, INCONCLUSIVE,
CI [-0.240,+0.233] on 1,381 aligned events over 1,031 reclaim session-dates
— remains published unamended alongside everything below. theta=0.2R and the
three outcomes are NOT amended.

## 0. Offline replication gate (passed 2026-08-25, zero cloud cycles)
10,000 resamples jointly clustered by reclaim session-date reproduce:
raw mean -0.0091R, CI [-0.2414,+0.2263] -> INCONCLUSIVE; winsorized +-5R
mean -0.0582R, CI [-0.2173,+0.0967] -> NULL. Top-9 ret_r events sum to
+206.3R against a whole-sample total of -12.58R; the +71R extreme implies
a stop ~1/71 of the 120-minute move — not executable.

## 1. Tradability floor on risk_dist (THE correction)
An event is population-conformant only if its stop distance satisfies BOTH:
  - >= min_stop_ticks[instrument] ticks, AND
  - >= floor_atr_frac * ATR(14, 5m) at arm time (per instrument)
Minimum executable stop declared BEFORE data: NQ/MNQ/ES 8 ticks (2.00/2.00/
2.00 pts), YM 6 ticks (6 pts), RTY 12 ticks (1.20 pts); floor_atr_frac =
0.10 for all instruments. Floored-primary is reported ALONGSIDE the frozen
unfloored result; both use the unamended theta/outcome rule.

## 2. Identical strategy/data
Same signal, parameters, markets (NQ/ES/YM/RTY), horizons (30/60/120/240m),
threshold (0.2R), and 2010-01..2024-12 dev segment as e19b-provisional.
Validation/holdout remain LOCKED.

## 3. Complete event ledger (replaces reduced chart points)
Per event: permanent event_id, reclaim session date, side, timestamps,
entry, stop, risk_dist, returns (per horizon), MFE/MAE, shadow labels
(CISD/FVG/IFVG bitmask), rollover/censor flags. One verified row per event
per horizon. Delivery channel: additional chart series keyed on the same
x-timestamp (`rd`, `mfe`, `mae`, integer shadow-bitmask series), because
ObjectStore export is license-blocked at this tier. `n_event_rows` emitted
as RuntimeStatistic and asserted == rows retrieved.

## 4. Analysis corrections (pre-declared)
- 10,000 resamples jointly clustered by reclaim session date across all
  markets (matches offline replication).
- Counter-arm documented as its actual separate bias-opposed population:
  arm:"counter" coincides with bias_aligned:false (2,375 rows) — the real
  control; redundant labels noted, both retained in ledger for clarity.
- n, session count, SD, SE, CI, MDE calculated from data (no hardcoding).
- Deterministic checksums + invariants emitted with the analysis.

## 5. Outcome rule (unamended)
POSITIVE (CI_lo > 0.2R): opens capped 6-8-run rescue study with pure,
friction-carrying simulator. NULL (CI_hi < 0.2R): family ARCHIVED including
the bias-gate finding (aligned -0.058 vs bias-rejected +0.096 at H*,
z=-1.78). INCONCLUSIVE: neither rescue nor optimization permitted.
