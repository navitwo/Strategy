# RTC2 SAME-DATE RANDOM-TIME FT CONTROL — FROZEN PREREGISTRATION

**Status:** FROZEN BEFORE REMOTE COMPILE OR EXPORT. No RTC1/RTC2 random-time
cloud run existed when this revision was authored. The only authorized remote
experiments are the four no-order development exports specified below.
Strategy backtests, optimization, validation, and holdout remain locked.

## Question and estimand

Does the corrected E19B-R aligned H=120 sweep/reclaim first-touch surface differ
materially from a control observed at a random time on the same market and
session date with the same `risk_dist`?

This is a **same-market/date composite control**, not a timing-only causal
control. The committed FT32E transport did not retain actual long/short side,
so the control side is an independent deterministic 50/50 draw. A difference
can therefore reflect event timing, event direction, or their interaction. A
similarity can rule out only the preregistered effect size in this tested
composite; it cannot prove equality, prove a martingale, or establish that
short-horizon geometry explains every candidate generator.

This is a no-order diagnostic. It has no entry, fill, fee, strategy PnL,
optimization, validation, or holdout path.

## Frozen population and randomization

- Instruments, in order: `NQ`, `ES`, `YM`, `RTY`.
- Dates submitted: `2010-01-01` through `2024-12-31`, `run_segment=dev`.
- Each aligned E19B-R H=120 source row contributes its market, unique source
  session date, and exact observed `risk_dist`.
- On that same market/date, one completed five-minute bar EndTime is drawn
  exactly uniformly from the 30 literal endpoints
  `09:30, 09:35, ..., 11:55 ET`, i.e. `09:30 <= EndTime < 12:00`.
  The 09:30 endpoint is intentionally the completed 09:25–09:30 bar.
- Control side is an independent exact-uniform two-way draw, long or short.
  Realized side counts are reported; 50/50 is an expectation, not a forced
  sample balance.
- SHA-256 rejection sampling, not modulo reduction, maps the frozen seed into
  the time and side draws with separate domain labels.
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

Frozen counts:

| Market | Source/control pairs |
|---|---:|
| NQ | 388 |
| ES | 186 |
| YM | 376 |
| RTY | 171 |
| **Total** | **1,121** |

Canonical market/date/risk control-spec SHA-256:
`ffe421865ae846f951eba343c522b7932b57c793e51cc99f7df53af954b2ead1`

Canonical risk-only SHA-256:
`58a9e24dfda4cba5dd8f3509fc81e7b9a59dd7586b098d76048c04e8dea31239`

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
- 1-bit randomized side;
- 5-bit observed path-bar count (must equal 24);
- 5-bit selected window index (must be 0–29).

The total payload is at most 52 bits and is emitted on the reused
`E19B-FT/a` transport series. The chart x-value is the selected reference
EndTime, not the resolution time. Offline decoding reconstructs source date,
source chart identity, risk distance, randomized side, selected time index,
path count, FT32 codes, and all 16 outcomes. Series `a` is a transport channel
only for RTC2 and does not assert bias alignment.

## Nulls and descriptive martingale calibration

The **population-comparison null** is that the paired sweep and same-date
composite-control surfaces have no material difference under the frozen
metrics and tolerances below. This is separate from a martingale hypothesis;
a martingale assumption alone does not imply equality after conditioning on a
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
FT ledgers plus `e19br_ft_results.jsonl`.

Construct max-deviation bands per metric family across all 16 cells of each
family:

1. the lower ambiguity-difference endpoints
   `sweep_pessimistic - control_optimistic`;
2. the upper ambiguity-difference endpoints
   `sweep_optimistic - control_pessimistic`;
3. the decision-rate differences; and
4. the ambiguity-rate differences.

Families 1–2 are calibrated jointly with one 97.5% max-deviation critical
value, and families 3–4 jointly with a separate 97.5% max-deviation critical
value. The reported label therefore controls the family-wise error at 2.5%
within the payoff family and within the rate family, but does not claim joint
coverage across both families; that limitation is emitted in the artifact's
`bootstrap_method` field and is part of this frozen rule.

Frozen tolerances:

- economically material payoff difference: `0.2R` gross per unit risked;
- decision-rate and ambiguity-rate equivalence: 5 percentage points.

Labels:

- `EVENT_SELECTION_SURFACE_DIFFERS_MATERIALLY`: at least one cell's
  simultaneous lower-endpoint band lies wholly above `+0.2R`, or its
  simultaneous upper-endpoint band lies wholly below `-0.2R`.
- `SURFACES_EQUIVALENT_WITHIN_PREREGISTERED_TOLERANCES`: every cell's full
  ambiguity-difference bands lie inside `[-0.2R,+0.2R]`, and every decision-
  and ambiguity-rate band lies inside `[-0.05,+0.05]`.
- `INCONCLUSIVE_SURFACE_DIFFERENCE`: every other outcome.

The first label is evidence that this event-plus-direction population changes
at least one tested barrier cell; it is not automatically a tradable edge or a
causal timing effect. The second rules out the preregistered material
difference only for this tested same-date composite and supports redirecting
Campaign 2 without claiming mathematical equality. The third authorizes
neither branch. Gross cell means do not include friction; `0.2R` is the frozen
campaign-level economic reference, not an exact per-event cost estimate.

## Fail-closed gates

Each market must satisfy all of the following before any row counts as evidence:

1. terminal `Completed` status and no runtime error;
2. exact instrument, dates, dev segment, window, experiment hash, seed, spec
   version, control-spec SHA, risk-spec SHA, and empty predicate list;
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
   path count 24, unique `(instrument, chart_x)` identities, and every chart
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
fail before creation. Exactly four full development exports are authorized;
no discovery-family export, smoke export, strategy backtest, optimization,
validation, or holdout run is authorized.
