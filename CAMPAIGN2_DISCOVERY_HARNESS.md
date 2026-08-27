# Campaign 2 Discovery Harness

**State:** infrastructure only. No Campaign 2 hypothesis has been selected. No
strategy backtest, discovery export, optimization, validation, or holdout run is
authorized by this document.

## Purpose

The bottleneck is now idea quality rather than event-study mechanics. The
existing development-only apparatus can therefore classify one reconciled
sweep/reclaim population into several predeclared event families and apply the
same 16-cell ordered first-touch grid to all of them in one market pass.

## Stable base population

Predicates run exactly once after a candidate has passed:

1. scale-normalized penetration minimum;
2. cumulative depth maximum;
3. reclaim confirmation;
4. tradability floor on stop distance.

They do not place orders, alter the side, change stop construction, resolve
barriers, or access future bars. A rejection consumes the same physical attempt
and preserves the attempt/sweep/reclaim funnel.

## Predicate contract

`event_predicates.py` exposes a versioned registry. Each predicate receives a
fresh read-only-by-convention context containing:

- `side`;
- `bias_aligned`;
- `risk_dist`;
- `sweep_depth`;
- `reclaim_bars`;
- `shadow_cisd`, `shadow_fvg`, and `shadow_ifvg`.

A predicate returns a boolean. Configuration accepts an ordered comma-separated
list of one to ten unique registered names. Unknown, duplicate, empty, and
more-than-ten lists fail before data processing. `discovery_only` additionally
requires `sweep_reclaim_v1` as bit 0 so every transported row proves membership
in the common base population. Legacy `events_only` accepts exactly one
predicate because its uint32 carries no family mask; trading variants reject
non-default predicates rather than ignore an inactive parameter. The ordered
list is included in canonical experiment identity and emitted as a
RuntimeStatistic. The omitted/default
base predicate is removed from non-discovery identity serialization, preserving
the legacy experiment hashes.

The initial registry contains six mechanical classifiers, not six selected
hypotheses:

- `sweep_reclaim_v1` — complete admitted base population;
- `bias_aligned_v1`;
- `bias_opposed_v1`;
- `shadow_cisd_v1`;
- `shadow_fvg_v1`;
- `shadow_ifvg_v1`.

New families require a versioned registry entry and a frozen rationale before
any discovery run.

## One-pass transport

Legacy `events_only` remains the audited FT32E channel: one uint32 containing
16 two-bit first-touch codes.

`discovery_only` extends that value without changing the FT32 low bits:

```text
bits  0..31  = sixteen 2-bit first-touch cells
bits 32..41  = up to ten predicate-match bits
```

The resulting 42-bit unsigned integer is below `2^53` and therefore exactly
representable in float64. It uses the same `E19B-FT/a` series identity that
already survives the hosted global series-name quota. `discovery_screen.py`
polls the declared chart count with explicit bounds, decodes each chart point
once, verifies the runtime predicate manifest and unique `(instrument,
chart_x)` identities, and reconstructs a separate cell screen for every
matched family.

## Required gates for any future authorized run

1. Development dates only; validation and holdout remain locked.
2. One canonical ordered predicate list frozen before launch.
3. Four market exports only: NQ, ES, YM, RTY.
4. Every cloud `n_ft_rows` equals retrieved rows; no empty aggregate when event
   results exist.
5. Unique `(instrument, chart_x)` identities.
6. Every payload is integral, non-negative, below `2^42`, and round-trips
   exactly through float64.
7. FT low 32 bits satisfy all existing decode, ambiguity, and monotonicity
   tests.
8. Each family count equals the number of rows carrying its bit; overlaps are
   explicit and never treated as independent samples.
9. Sample size, ambiguity rate, and undecided rate precede economics.
10. Screens are exploratory candidate triage. No optimization or strategy run
    is unlocked without a fresh preregistration and an economically meaningful
    no-order result.

## Scope limit

This is an admission-predicate bank over the current sweep/reclaim event
generator. It can cheaply compare five to ten subfamilies sharing the same
market data, side, stop normalization, and forward path. It does **not** yet
generate arbitrary opening-range, longer-horizon, cross-instrument,
relative-value, cross-sectional, or volatility events. Those directions relax
important constraints but require separate versioned generators or data
adapters before they can use the common resolution and reconciliation layer.
