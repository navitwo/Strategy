# C2-RESIDUE-STOPWIDEN — offline probe: does GC's overnight-high continuation survive a wider stop?

**Purpose:** decide, before any purchase and before any Campaign 3
pre-registration, whether the C2 archive residue (GC continuation on
overnight-high touches) can ever clear friction under ANY wider-stop
geometry, or is dead at all of them. Free: recomputes from the committed
ledger `c2_local_study.json` only. No Databento, no cloud, no re-decode,
no backtest of any strategy, no parameter selection.

**Run:** `python c2_residue_stopwiden.py` → `c2_residue_stopwiden.json`
+ stdout report. Permanent mirror test: `test_c2_residue_probe.py`.

## Frozen decision rule (committed BEFORE results exist)

**Target-family ambiguity, resolved by running both.** The instruction
"stops of 0.5/1.0/1.5/2.0 ATR, holding the target at 2× the stop"
describes two different grids depending on what "2x" scales:
- **Family A (C2-compatible):** target fixed at 2 R (the frozen T2;
  1 R = 1 ATR in C2 units), stop s' ∈ {0.5, 1.0, 1.5, 2.0} R. The
  s'=0.5 row IS the committed C2 cell — self-check: extreme-based
  emulation must land near the archive's GC overnight-high contrast
  (−0.0610). Any gap is NOT a bug to hide: it is the direct measurement
  of the first-touch-blind bias of this emulation (bar-path ordering vs
  window extremes), reported as the `baseline_gap` diagnostic.
- **Family B (constant 2:1 ratio):** target = 2·s', stops as above. The
  s'=0.5 row is NOT C2 (target 1 R ≠ 2 R); it is a new geometry
  family included because "2x the stop" literally says so.

Statistics: GC, `level_kind == overnight_high`; contrast = reversal −
continuation payoff, expressed in ATR points (scale-free) AND per unit
risked (= ATR contrast / s'). Estimator: the archive's declared
exploratory convention (point = event mean, CI = session-cluster
bootstrap, 4000 draws, seed tag `C2-RESIDUE-v1:` + family + s').

**The scaling identity (why the raw barrier contrast is the verdict
statistic).** Friction is a fixed physical cost ≈0.2 R_base = 0.2 ATR.
Margin per unit risked = |c(s')|/s' − 0.2/s' = (|c(s')| − 0.2)/s'. The
SIGN of margin depends only on |c(s')| vs 0.2 ATR — widening the stop
shrinks friction and effect by the same scale. Wider stops rescue an
effect ONLY by changing the payoff distribution itself (deep-MAE
losers surviving instead of stopping out). That survival effect is what
this probe measures; the R-unit improvement alone is bookkeeping.

**Reported per cell:** contrast (ATR), its pessimistic and optimistic
bracket (see Limits-1: first-touch ordering unknown when both barriers
lie inside the window — pessimistic resolves stop-first, optimistic
target-first; truth is inside the bracket), ambiguity share (fraction
of events where both are touched), per-unit-risked figure, CI under the
archive convention, friction fraction 0.2/s', and margin (|c|−0.2)/s'.

**Horizon interaction.** Barrier resolutions exist only where window
extremes exist: the 120m primary path. For the hold-vs-stop view the
probe ALSO reports the time-exit analogue at 30/60/120/240m (contrast
= 2·fwd_R per the two-arm close symmetry), which is stop-blind by
construction and explicitly shows that a pure time exit cannot create
margin the effect doesn't already have in ATR terms.

Verdict branches (applied to family A, GC overnight-high, with family B
and NQ overnight-high reported alongside as context):

- **DEAD** — the continuation contrast decays toward zero or inverts as
  s' widens (even in its OPTIMISTIC bracket at s'=1.0: if the optimistic
  bound fails, the truth necessarily fails). Record plainly in the
  archive, close the residue; next campaign starts from a fresh idea.
- **VIABLE-BOUND (upper bound only)** — contrast holds/strengthens in
  the continuation direction at s'=1.0 in its PESSIMISTIC reading (the
  conservative side of the bracket), does not invert at 1.5/2.0, AND at
  least one (s', family-A) cell has |c(s')| > 0.2 ATR with the whole CI
  outside the friction line. This licenses *drafting* a Campaign 3
  pre-registration with specified geometry. It does NOT license
  believing the effect — see Limits.
- **INCONCLUSIVE** — anything else: sign holds but no cell clears 0.2
  ATR even optimistically-bracketed, or the bracket is too wide to say.
  Residue remains real-but-not-tradable; archive stays closed; a fresh
  hypothesis is the default next cycle.

The rule may not be edited after results exist. If results land between
branches, the more conservative reading governs.

## Limits (stated before running, binding on reading)

1. **Upper-bound only.** The ledger carries window extremes (`mfe_R`,
   `mae_R` over the primary 120m path) and fixed-horizon closes
   (`fwd_R`), NOT the per-bar path. A wider barrier may have been touched
   and released inside a bar window the extreme alone cannot order — the
   exact first-touch-ordering defect that invalidated the Campaign 1
   screen. The emulation resolves same-event ambiguity pessimistically
   (stop-first), and the horizon profile is derived by clipping the
   120m-window extremes through the wider barrier: a
   BOUNDING reconstruction, not a replay. Favourable numbers here are
   NOT evidence of an effect; they only fail to rule it out.
2. An exact answer to "wider stop" requires re-resolution from the bar
   path at the new grid — a fresh first-touch computation. That is a
   pre-registered successor's §2 data, not this probe's job.
3. Exploratory in its entirety: one market, post-hoc, derived from a
   family of 12+ comparisons (the archive's horizon and touch splits).
   Its prior is weak. A fresh hypothesis is an explicitly legitimate
   alternative use of the next cycle regardless of what this probe says.
4. Nothing here promotes anything, opens validation/holdout, or spends
   money. SI/PL/HG are declined by user decision; the inferred balance
   ≈$86.64 is reserved for a possible ES/YM/RTY index-complex pull if a
   later hypothesis warrants it; credits expire 2027-02-09 regardless.
