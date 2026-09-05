# ERL→IRL GATE-ABLATION STUDY — protocol (pre-results, 2026-09-05)

Status: FROZEN BEFORE ANY LADDER NUMBER EXISTS (commit ordering proves
it). Character: exploratory; zero promotion power; no Campaign 3
pre-registration drafted in this pass. θ = 0.2R fixed program-wide
economic reference; the hypothesis-specific friction arithmetic of §1
governs what "clears cost" means here. Spend: $0.00, data already
owned. Validation/holdout locked and unread. No optimization, no
parameter selection: every rung parameter is fixed in §3 now.

## 0. Why this run exists (recorded plainly, per directive)

The ERL→IRL playbook is ≈85% identical to Campaign 1's SCIFVG: ERL
sweep = liquidity sweep; displacement = CISD; retracement-into-FVG =
the retest entry; stop below sweep low = C1 stop_mode="sweep"; 2R
target. Three real differences: (i) 30m/1H bars rather than 5m;
(ii) FRESH FVG rather than the inverted-FVG gate; (iii) a variable
target at real opposing liquidity with a 2R skip filter, rather than
a fixed 2R.

**Case FOR testing it.** First hypothesis in this program that can
pass the friction test. Median NQ 30-minute ATR(14) in the committed
C2 ledger is **14.2857 points** (verified from c2_local_study.json;
GC: 3.1464). Against the declared ~1.0-point NQ round-trip cost,
friction is **0.140R at 0.5×ATR stop, 0.070R at 1.0×ATR, 0.035R at
the ~2.0×ATR structural sweep-low stop** — versus the 0.2R floor that
killed Campaign 1's 5-minute implementation and the ~0.5R that priced
out absorption. (The 1.0-pt round-trip is a declared assumption from
the C1-era cost model; PROTOCOL anchoring rule: sensitivity range
[0.8, 1.2] pts keeps friction ≤ 0.171R at 0.5×ATR and ≤ 0.086R at
1×ATR — under 0.2R at every stop width the playbook uses.) GC is the
weaker venue for the same arithmetic: 1.0 pt against median
ATR 3.1464 is 0.318R even at 1×ATR — recorded before running.

**Case AGAINST.** Campaign 2 already measured this strategy's entry
trigger — a sweep of overnight/prior-day levels — on 30-minute bars
across 3,033 NQ events and 15 years, finding CONTINUATION at
−0.1846R, strengthening with hold time (NQ 240m ≈ −0.161,
significant). Campaign 1 found the gate chain won 17.4% against
random entry's 34.9%, and ablating the inverted-FVG produced its best
variant. The base rate opposes the premise and the gates subtracted —
**but both findings came from 5-minute bars where friction dominated,
and the gates have never been measured at 30m/1H where they have
room.** That is precisely the open question.

## 1. Population and data (zero new data, zero spend)

The committed C2 event population: 3,033 NQ + 2,468 GC first-touch
events (overnight high/low; DEV 2010-06-07..2024-12-31), replayed
against the same guard-verified local Databento 30-minute bar series
`c2_local_study.py` uses. Events match by (session_date,
level_kind, event_et); two soundness gates abort on failure: (a) the
replay reproduces every committed `event_et` for 100% matched events
with matched count = committed count; (b) re-resolving rung 1
reproduces the committed `contrast_R` per event exactly. Both markets
are analyzed and reported as SEPARATE verdicts; never pooled.

## 2. Look-ahead guard (the Campaign 1 defect class — four prior hits)

Every event is stamped at the bar that COMPLETES the condition needed
to know it; gate logic is a pure function of the bar prefix ending at
its own stamp; outcomes are measured strictly forward over bars with
index > stamp index. Retracement entry (rung 4) is a boundary touch
inside its stamp bar with the unambiguous ordering precondition of
§3; all payoffs start at the NEXT completed bar — the C2 touch-bar-
exclusion convention (c2_local_study.py:34–37) that produced the
defect-free fwd_R cells. A PERMANENT test
(`test_erlirl_ablation_lookahead.py`) pins this: it plants
distinctive values into bars at/after each gate's stamp and fails if
any earlier gate's output changes — shipping BEFORE the ladder runs.

## 3. The ladder (all parameters frozen now)

Shared frame for rungs 1–4 (comparability with C2): risk unit
R_ATR = the event's committed ex-ante `atr_points`; arms and payoffs
exactly as C2 — reversal arm vs continuation arm (side = reversal
side: +1 at overnight_low, −1 at overnight_high), target T=2.0R_ATR,
stop S=0.5R_ATR, resolution window = 4 completed bars after the
stamp (= 120 min), same-bar ambiguity pessimistic (stop-first),
per-arm winsorized (−0.5, +2.0) so contrast ∈ [−2.5, +2.5].
contrast = reversal − continuation; **positive = reversal favored =
the playbook's predicted direction**. The rung-1 sweep-only baseline
on NQ carries committed cluster-mean −0.1846R (continuation).

- **Rung 1 — sweep only.** The committed C2 event; stamp = touch
  bar; entry = level (identical to C2 primary by construction).
- **Rung 2 — + displacement.** From each rung-1 event, the
  DISPLACEMENT bar d = first completed bar after the touch bar whose
  CLOSE is back across the level (high touch: close < level; low
  touch: close > level), within deadline 6 bars. Stamp = d; entry =
  level (declared simplification keeping rung 2 comparable to rung
  1 — the rung isolates the displacement gate's marginal effect on
  the SAME trade definition). Outcomes = 4 bars after d. Events with
  no displacement bar by deadline drop from rungs 2–4.
- **Rung 3 — + fresh FVG.** At a rung-2 event: a fresh gap created
  by the displacement leg itself. For a low touch (long reversal):
  the displacement bar jumps clear of the touch bar —
  `d.low > touch.high`, gap zone (touch.high, d.low),
  gap_hi = d.low. Mirror for high touch (`d.high < touch.low`,
  gap zone (d.high, touch.low), gap_lo = touch.low). A gap requiring
  a whole-bar jump is the strictest bar-level reading of "the
  displacement leaves a void" — declared, not tuned. Stamp = d (the
  bar completing the gap); entry/arms/window as rung 2.
- **Rung 4 — + retracement entry.** From rung 3: the first
  completed bar r after d that retraces INTO the gap from the
  correct side: low-touch case r.open ≥ gap_hi and r.low ≤ gap_hi
  (open above the boundary, pierce into it — unambiguous first
  touch; a bar that both pierces AND closes below gap_lo, having
  jumped the whole void, is kept with its fill still at gap_hi since
  the boundary order is fixed by the open precondition); fill =
  gap_hi (mirror: gap_lo). Deadline 6 bars after d; events failing
  the deadline or never opening on the far side drop. Stamp = r;
  outcomes = 4 bars after r; risk unit still R_ATR; **this rung's
  entry price is the gap boundary, not the level** — it is the
  playbook's actual trade.
- **Entry-convention sensitivity (carried from C2):** rungs 1–4 are
  additionally resolved with touch-bar-close entry for the level-
  frame rungs and with r.close for rung 4 (`tc` variant), reported
  as event means only — never verdicts.

## 4. Variable target + 2R skip arm (never measured; rung 5)

On rung-4 events (playbook geometry, structural risk):
stop = sweep-extreme (touch bar low for long reversal / high for
short) + 0.5×ATR buffer; risk_points = |entry − stop| (floor
0.25×ATR to bound degenerate gaps). Opposing liquidity = the lowest
LOW of the 20 completed bars strictly before the touch bar (mirror
for shorts). Variable target = nearer of (entry ± 2×risk_points) and
the liquidity level; **skip filter: SKIP the trade if the liquidity
level is farther than 2×risk or absent** (quantified selection
effect: report skips, and among non-skips how often liquidity bound
the target below 2R). Payoff: first-touch over the 4 completed bars
after the fill stamp, stop-first ambiguity, payoff in R_STRUCT =
payoff_points / risk_points (no winsorization needed: by
construction payoff ∈ [−1, +2] R_STRUCT, the target being the nearer
arm). Paired baseline: same events with fixed-2R target, no skip.
Report for both arms: cluster mean, points mean vs 1.0-pt friction,
n, sessions, clustered CI. This arm's contrast against the fixed-2R
arm IS the measurement of the rule "that has never been measured".

## 5. Inference

Estimator identical to C2 `clustered_ci`: mean of session-date
cluster means, 399 resamples, percentile 2.5/97.5 method=lower,
independent seeded streams ("ERLIRL-ABLATION-2026-09-05" + market +
rung label). Assertion `sessions < n` enforced wherever a CI is
printed; rungs with n < 30 print counts only; the §6 flip test itself
requires n ≥ 100 (frozen — set before results).

## 6. Kill rule — FROZEN NOW, BEFORE ANY NUMBER EXISTS

Primary flip test per market: for rungs 2, 3, 4 (level/gap-entry
contrast) and rung 5 vs fixed-2R baseline — a **SIGN FLIP** = that
rung's contrast CI lies entirely ABOVE +0.0R with n ≥ 100. Evaluated
against zero (direction is the premise), with friction clearance
reported separately, never as the flip condition.

- **DEAD (default):** no rung flips on either market → ERL→IRL is
  recorded dead on its own gates, closed here; no Campaign 3
  pre-registration; next campaign starts fresh.
- **FLIP:** any rung flips → report surviving n, effect vs the §1
  friction range (0.035R–0.140R NQ at 30m stop sizes), the full
  funnel drop at that rung, and the multiple-comparison caution
  (≈16 looks defined in §3; a flip anywhere is screening, not
  confirmation). ONLY on this branch, and only after the user signs
  off on this report, is a Campaign 3 pre-registration drafted with
  frozen primary, bounded estimator, θ, feasibility proof, declared
  exploratory boundary.
- A rung merely shrinking the negative contrast is descriptive; it
  never licenses a prereg.

## 7. Required statements in the write-up

Funnel-first (n at every rung before any mean); NQ and GC separate;
§0 both cases; the friction arithmetic anchored to committed medians;
every payoff is 30-minute-bar resolution, so seconds-scale execution
reality (queue position, fast-market slippage through the level) is
OUTSIDE this measurement in both directions — it can neither rescue
nor condemn a flip here, only the friction ceiling of §1 can.
