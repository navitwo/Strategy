# RTC2 SAME-DATE RANDOM-TIME FT CONTROL — FROZEN PREREGISTRATION

**Status:** FROZEN BEFORE REMOTE COMPILE OR EXPORT. No RTC1/RTC2 random-time
cloud run existed when this revision was authored. The only authorized remote
experiments are the four no-order development exports specified below (plus the
side-capture events-only pass described in the amendment). Strategy backtests,
optimization, validation, and holdout remain locked.

## Pre-data amendments (2026-08-28)

Four pre-data specification corrections, each dated and recorded before any
random-time data was drawn:

1. **Single-convention comparison.** The original rule built each cell's
   difference band as `[sweep_pessimistic − control_optimistic,
   sweep_optimistic − control_pessimistic]`, stacking two worst-case ambiguity
   brackets. Offline from the committed FT32E ledger the sweep-side ambiguity
   width alone is 0.3133R at T0.5/S0.5, 0.1914R at T1/S0.5, and 0.1452R at
   T1.5/S0.5, so the equivalence label was structurally unreachable (T0.5/S0.5
   consumes 78% of the 0.4R budget before any bootstrap or multiplicity term).
   The primary comparison now uses a **single resolution convention** —
   pessimistic, ambiguity priced stop-first — with the optimistic version as a
   declared sensitivity endpoint only. The resulting band is a genuine
   simultaneous max-deviation bootstrap critical value across all 16 cells
   (97.5% quantile of the max cell deviation under a joint date-cluster
   bootstrap), which measured **0.1974R** pre-data from a conservative
   independent-draw null pairing and is under the 0.2R equivalence budget, and
   matches how `e19br_ft_screen.json` reports. (A per-cell 1.96·SE interval
   would be ~0.075R median; the max-deviation critical value already carries
   the 16-way multiplicity and is the correct, frozen multiplier.)
2. **Economic threshold anchored on the pessimistic best cell.** The tri-state
   rule carries the 0.2R θ discipline: a material difference whose sweep
   surface does not clear 0.2R round-trip friction is NULL for decision
   purposes. The anchor is the **pessimistic** best cell (+0.0648R, far below
   friction), not the optimistic bound — the four-event holiday exclusion moves
   the optimistic best from 0.1968R to 0.2011R, straddling the threshold, which
   is exactly the knife-edge that motivates anchoring θ on the pessimistic
   primary convention.
3. **Holiday-session exclusion.** Four primary H=120 events reclaim outside the
   frozen window on US market holidays (2011-02-21, 2018-02-19, 2022-06-20),
   admitted by the window filter as a conformance defect. They are excluded
   symmetrically from the control and the sweep side of the comparison
   (N 1,121 → 1,117), logged as an E19B-R conformance finding, and published as
   `e19br_ft_screen_1117_sensitivity.json` beside the frozen full screen.
4. **Empirical slot matching.** The event population is not uniform over the
   30 window slots (sweeps concentrate near the open). The control slot is now
   drawn from the empirical E19B-R slot histogram, excluding each source
   event's own slot plus a one-bar buffer, and both slot histograms are
   published in the artifact. The explicit slot histogram is frozen as
   `SLOT_SPEC_SHA256`.

## Question and estimand

Does the corrected E19B-R aligned H=120 sweep/reclaim first-touch surface differ
materially from a control observed at a random time on the same market and
session date with the same `risk_dist`, the same side, and the empirical slot
distribution?

This is a **same-market/date/time-of-day/side matched control**. The committed
FT32E transport did not retain actual long/short side, so side is recovered by
a side-capture pass (see below) and then matched exactly per event. With side
matched, a difference isolates event timing and setup structure; a similarity
still cannot prove equality, prove a martingale, or establish that every
generator is foreclosed.

This is a no-order diagnostic. It has no entry, fill, fee, strategy PnL,
optimization, validation, or holdout path.

## Side capture (option A — drift-bound evidence)

Per-market 09:30→12:00 drift was measured before choosing a side policy. Daily
open→close log returns 2010–2024 (Yahoo index series) are positive, not flat:
NQ +2.733 bp/day, ES +2.453, YM +2.408, RTY +1.457. Scaled to 120 minutes and
divided by median risk_dist this is **0.097R (NQ), 0.056R (ES), 0.056R (YM),
0.024R (RTY)** — an order of magnitude above the 0.01R threshold in every
market. **These headline figures are pure-long drift** (a 100%-long position).
The actual confound at a realistic long/short skew is `(2·p_long − 1) ×
drift_R`: at a 60/40 skew that is 0.019R, and at a 70/30 skew 0.039R. Side
capture is therefore justified not by the headline magnitude but by being
*inside the ±0.2R comparison window while remaining permanently useful* —
the confound is small enough that it cannot fabricate a material difference,
yet capturing side exactly removes it as an assumption and costs nothing in a
no-order pass. Side is NOT left as a randomized 50/50 draw. Instead a
**side-capture events-only pass** re-derives the E19B-R aligned H=120 events
and captures each event's numeric side (±1), its explicit reclaim timestamp,
and a session-type flag, all in one pass. The control side is then matched to
each captured event side exactly. The captured side ledger is committed before
the RTC2 export and its SHA-256 is frozen into the control spec.

**Side-capture fail-closed population gate.** Because the side-capture pass is
a re-derivation of a frozen artifact, it must reproduce the frozen 1,121-event
FT32 population byte-exactly before its captured side/session bits are used:
same per-market counts (NQ 388, ES 186, YM 376, RTY 171), same chart_x
identities, same codes, and same packed_uint32. Any differing event means the
engine is not deterministic across the side-capture change, and the correct
response is STOP, never reconcile. The low 32 payload bits must remain FT32E
byte-identical; side and session-type are packed into bits 32 and 33 above the
FT32 vector, keeping the total payload below `2^52`.

## Frozen population and randomization

- Instruments, in order: `NQ`, `ES`, `YM`, `RTY`.
- Dates submitted: `2010-01-01` through `2024-12-31`, `run_segment=dev`.
- Each aligned E19B-R H=120 source row (after the four-event holiday exclusion)
  contributes its market, unique source session date, exact observed
  `risk_dist`, and exact captured side.
- On that same market/date, one completed five-minute bar EndTime is drawn from
  the **empirical E19B-R slot histogram** over the 30 literal endpoints
  `09:30, 09:35, ..., 11:55 ET` (`09:30 <= EndTime < 12:00`), excluding the
  source event's own slot plus a one-bar buffer. The 09:30 endpoint is the
  completed 09:25–09:30 bar.
- Both the sweep and the control slot histograms are published in the artifact.
- SHA-256 rejection sampling, not modulo reduction, maps the frozen seed into
  the **slot draw only**. The side is NOT drawn: it is matched to each source
  row's exact captured side from the committed side-capture ledger (see
  "Captured side" below). Only the slot draw uses exact weighted rejection
  sampling over the frozen histogram.
- Frozen root seed: `RTC2-20260827-v1`.
- Predicate list: `[]` exactly. Any non-empty runtime `event_predicates`
  invalidates the run.
- Reference price: the selected completed-bar close.
- Horizon: exactly 120 elapsed minutes and exactly 24 subsequent contiguous
  five-minute bars. The selected bar's own high/low is never observed.
- Only a completed bar whose EndTime is a literal five-minute grid point
  (minute divisible by 5, zero seconds and microseconds) may count toward
  eligibility or selection; any other EndTime fails the run.
- A duplicate, out-of-order, missing, non-five-minute, early-close, or
  horizon-slippage path fails the run rather than resolving on a later bar or
  redrawing a timestamp.

Frozen counts (after the four-event holiday exclusion):

| Market | Source/control pairs |
|---|---:|
| NQ | 385 |
| ES | 185 |
| YM | 376 |
| RTY | 171 |
| **Total** | **1,117** |

Canonical market/date/risk control-spec SHA-256:
`65b05e0f4c3d1d3f40e766b6b20990115c998e8091b759cc15232cbb066a4856`

Canonical captured-side SHA-256 (SIDE_SPECS, nested by instrument then
`chart_x`; `chart_x` collides across markets so the key is never flat):
`1b2b0364a2a98ac964d8242a06aa96d7a61ffca9f318391875f6bad2e4d5c234`

Canonical risk-only SHA-256:
`b1fd70ed4f266b1ea1d11c72edbb947078f7394f18261ec22046de37b3c354e8`

Canonical slot-histogram SHA-256:
`47f7cf4b862b7de4677ce1d3d385fb9b71e3de36e304a2b75ac1f532c9adee2c`

Source event-ledger SHA-256 values:

- NQ: `914eeec63ed6a0229432d33bbcf4c0d18bc089abbe53e9a884bc24cf169c22e2`
- ES: `6c4e7e0367cda58d31c6387554b97cc22b7931ec004a8a9fe6e251becd59956a`
- YM: `0fc2d25d582928c8c17da0607dde7d633762d9d176325317ab4f87cc3d46fd84`
- RTY: `1d38bc5bd0382f931a5bece4ca396fb17205ed70772032e4a22072b6b9abd9b9`

## Frozen outcomes and exact transport

The grid is unchanged: targets and stops are each `(0.5, 1.0, 1.5, 2.0)` in
units of the paired source row's `risk_dist`, target-major then stop-minor.
The lower 32 payload bits remain FT32E exactly, two bits per cell:

- `0`: undecided by exactly 120 minutes
- `1`: target first
- `2`: stop first
- `3`: target and stop touched in the same five-minute bar

The upper 20 audit bits are exact in float64 and carry:

- 9-bit source-row index;
- 1-bit side;
- 5-bit observed path-bar count (must equal 24);
- 5-bit selected window index (must be 0–29).

The total payload is at most 52 bits and is emitted on the reused
`E19B-FT/a` transport series. The chart x-value is the selected reference
EndTime, not the resolution time. Offline decoding reconstructs source date,
source chart identity, risk distance, side, selected time index, path count,
FT32 codes, and all 16 outcomes. Series `a` is a transport channel only for
RTC2 and does not assert bias alignment.

## Nulls and descriptive martingale calibration

The **population-comparison null** is that the paired sweep and same-date
matched-control surfaces have no material difference under the frozen metrics
and tolerances below. This is separate from a martingale hypothesis; a
martingale assumption alone does not imply equality after conditioning on a
path-dependent sweep/reclaim event.

For each population, retain the idealized continuous-barrier calibration
`p_target=S/(T+S)` and its existing iid-binomial z/Holm diagnostics as
descriptive fields only. The permanent `formula_scope` caveat remains binding:
that expression assumes no overshoot and almost-sure eventual exit and is not
generally the target probability conditional on deciding within 120 minutes.
Those iid diagnostics do not drive the RTC2 comparison label.

Undecided and ambiguous paths are first-class surface outcomes. The report
must show decision and ambiguity rates for both populations in every cell.
Decided-path pessimistic/optimistic mean R remains reported for continuity,
but no match label can be earned from decided paths alone.

## Frozen paired inference and decision rule

Pair rows by exact `(instrument, source_index)` and cluster all observations by
source session date, jointly across markets. Use 2,000 deterministic paired
date-cluster bootstrap replications with seed
`RTC2-cluster-bootstrap-v1`. For every replication, resample dates with
replacement and preserve all market pairs and all 16 cells on each selected
date.

Before any comparison, the committed sweep evidence must regenerate exactly:
every sweep-ledger row must carry its instrument, ordered `ft_row`, `chart_x`
equal to the frozen control-spec identity, valid uint32 packing, codes, and
cells; per-market and pooled stop-width monotonicity must hold; and
`e19br_ft_screen.json` must be byte-equal to the payload rebuilt from the four
FT ledgers plus `e19br_ft_results.jsonl`. The four holiday-session events are
then excluded symmetrically from both the sweep and control populations.

The primary comparison uses the **pessimistic** resolution convention (same-bar
ambiguity priced stop-first) on both populations. Construct max-deviation bands
per metric family across all 16 cells of each family:

1. the pessimistic payoff differences `sweep_pessimistic − control_pessimistic`
   (primary);
2. the optimistic payoff differences
   `sweep_optimistic − control_optimistic` (declared sensitivity);
3. the decision-rate differences; and
4. the ambiguity-rate differences.

Family 1, family 2, and families 3–4 each use their own 97.5% max-deviation
critical value. The reported label controls the family-wise error at 2.5%
within each family but does not claim joint coverage across families; that
limitation is emitted in the artifact's `bootstrap_method` field and is part of
this frozen rule.

Frozen tolerances:

- economically material payoff difference: `0.2R` gross per unit risked;
- decision-rate and ambiguity-rate equivalence: 5 percentage points;
- economic threshold θ: `0.2R` against the sweep surface's **pessimistic** best
  cell.

Labels (four, with one non-decision fallback):

- `SURFACES_EQUIVALENT_WITHIN_PREREGISTERED_TOLERANCES`: every cell's
  pessimistic difference CI lies inside `[-0.2R,+0.2R]`, and every decision-
  and ambiguity-rate CI lies inside `[-0.05,+0.05]`.
- `EVENT_SELECTION_SURFACE_DIFFERS_AND_TRADABLE`: some cell's pessimistic
  difference CI lies wholly outside `±0.2R`, AND the sweep surface's pessimistic
  best cell clears `0.2R`.
- `EVENT_SELECTION_SURFACE_DIFFERS_BUT_NULL`: some cell's pessimistic difference
  CI lies wholly outside `±0.2R`, AND the sweep surface's pessimistic best cell
  sits at or below `0.2R`.
- `INCONCLUSIVE_SURFACE_DIFFERENCE`: every other outcome.

The first label supports redirecting Campaign 2 (matching surfaces mean the
first-touch structure belongs to the instrument class, not the event). The
second is the first positive signal in this project. The third is interesting
and untradable (a material difference below the friction threshold is NULL for
decision purposes). Gross cell means do not include friction; `0.2R` is the
frozen campaign-level economic reference.

## Fail-closed gates

Each market must satisfy all of the following before any row counts as evidence:

1. terminal `Completed` status and no runtime error;
2. exact instrument, dates, dev segment, window, experiment hash, seed, spec
   version, control-spec SHA, risk-spec SHA, slot-spec SHA, and empty predicate
   list;
3. exact reviewed-commit compile manifest binding compile ID, Git HEAD, and
   SHA-256 for every uploaded source file;
4. exact started, resolved, `d_ev_results`, `n_ft_rows`, retrieved-row, and
   frozen market counts, with `random_control_eligible` exactly
   `30 × market rows`;
5. zero invalid paths, cycles, submissions, fills, flatten activity, and
   residual order-purpose registrations, verified on the engine's actual
   RuntimeStatistic names (`d_cycles_opened`, `d_n_fillevents`,
   `f_L_submits`, `f_S_submits`, `f_L_fills`, `f_S_fills`,
   `f_flatten_fills`, `f_forced_flattens`, `eod_flattens`);
6. integral payloads below `2^52` with valid metadata and uint32 FT vectors;
7. every source index exactly once, exact source risk/side/window metadata,
   path count 24, unique `(instrument, chart_x)` identities, the selected
   window index outside the source event's own slot ± one bar, and every chart
   x-value equal to the frozen `(source_date, window_index)` endpoint in the
   platform's emitted time domain (naive-UTC-stamp and ET-stamp encodings both
   accepted; anything else fails);
8. non-empty, non-vacuous cells and non-decreasing
   `p_target_given_decided` as stop width increases for every fixed target,
   separately in every market and pooled, for the random rows and the
   regenerated committed sweep rows alike;
9. exact offline regeneration of the screen after rereading the four persisted
   ledgers and run records.

Duplicate-name protection: remote experiment names are checked before launch
and re-checked immediately before each `backtest_create`. The QuantConnect API
offers no atomic create-time uniqueness, so a truly concurrent second launcher
remains a residual operational risk that is mitigated by the single-invocation
launch discipline in this document (one driver process, four creates, no
manual parallel launch).

Before launch, this preregistration, hosted source bundle, driver, and permanent
tests must be committed, pushed, locally green, independently reviewed, and
byte-identical to the remotely compiled bundle. Duplicate experiment names
fail before creation. Exactly four full development exports are authorized
(after the side-capture pass); no discovery-family export, smoke export,
strategy backtest, optimization, validation, or holdout run is authorized.
