# ERL→IRL gate-ablation — results and disposition (2026-09-05)

Protocol: `ERLIRL_ABLATION_PROTOCOL.md`, frozen/committed BEFORE any
rung number existed (`41d88c6`, pre-results definition fix `ea7e0b5`).
Kill rule §6, decision inputs §3–§5, all sealed first. Zero spend.
Validation/holdout locked. Exploratory: zero promotion power.

## 0. Soundness (before any number)

Replay of the committed C2 population passed both frozen gates on both
markets: (a) replayed event set == committed set (3,033 NQ / 2,468 GC,
exact); (b) rung-1 reproduces every committed `contrast_R` to 1e-12,
and the touch-close sensitivity reproduces the committed ledger mean
byte-for-byte (−0.048632 NQ / −0.064830 GC). A first-pass crash of
gate (b) traced to a pairing bug in THIS script (two level-kinds
sharing one bar stamped one `event_et`); fixed before any statistic
was produced. The 14-test look-ahead guard
(`test_erlirl_ablation_lookahead.py`) is permanent and green.

## 1. Frozen ladder output (funnel first)

| rung | NQ n | NQ contrast cluster-mean CI | GC n | GC contrast CI |
|---|---|---|---|---|
| 1 sweep only | 3,033 (2,570 sess) | **−0.1846 [−0.2445, −0.1121]** | 2,468 | **−0.0958 [−0.1677, −0.0347]** |
| 2 +displacement | 2,108 | **+1.4053 [+1.3408, +1.4595]** | 1,719 | **+0.9793 [+0.9238, +1.0369]** |
| 3 +fresh FVG | **0** | n/a | **0** | n/a |
| 4 +retrace fill | 0 (inherits 3) | n/a | 0 | n/a |
| 5 variable target/skip | 0 | n/a | 0 | n/a |

Drop funnel NQ: 925 no-displacement; 2,108 no-void (100% of survivors).
GC: 749; 1,719 (100%).

Mechanical §6 verdict line: **FLIP — NQ rung2, GC rung2**
(CIs entirely > 0 with n ≥ 100; rungs 1 reproduce the committed
continuation record exactly).

## 2. Validity diagnosis (why the FLIP must not be read as evidence)

The directive ordered the look-ahead risk "guarded explicitly:
'require displacement, then enter the retracement' conditions on part
of the move having already occurred — exactly where Campaign 1 had
four separate defects." The bar-prefix structural guard means no gate
reads past its stamp, but rung 2's own definition conditions the
stamp on the move the payoff frame then measures:

1. **Continuation arm is pre-stopped.** Entry remains the LEVEL
   (frozen comparability choice); the displacement bar has already
   CLOSED past it. The continuation arm's stop sits 0.5×ATR beyond the
   level — inside or beside the move that just happened. Measured
   consequence: the continuation arm records −0.5 in **96.3%** (NQ) /
   **92.3%** (GC) of events, 18.9%/9.1% on the first post-stamp bar
   alone, while 60.2%/36.8% of contrasts pin at the +2.5 winsorized
   bound. Contrast (+1.41R) is ≈ (target-side 2.0) − (certain −0.5):
   the bracket's asymmetry (T=2R vs S=0.5R) applied to a
   path already known to favor one arm. It is an arithmetic
   consequence of selection + frame, not information about future
   prices, and no trade was ever available at that stamp (price had
   moved through the entry before the "entry").
2. **The strategy's actual chain was never observed.** The frozen
   void definition (`d.low > touch.high` for a low touch — a whole-bar
   jump clearing the touch bar's range) was satisfied by **zero**
   events: 0/2,108 NQ and 0/1,719 GC displacement survivors, with
   jump excess > 0.25/0.5/1.0 ATR likewise all zero
   (`erlirl_diagnostics.json`). No formal contradiction — both
   branches are geometrically possible — but the frozen form demands
   the first bar closing back across the level ALSO sit entirely
   beyond the whole touch bar, and first-touch bars at overnight
   extremes have median range 2.96× ATR (42.25 pts NQ): the joint
   requirement is an enormous jump candle that never once occurred
   (0/2,108 NQ, 0/1,719 GC, zero events at any positive jump
   excess). A design error caught only by the n=0 result — surfaced
   here, and the reason §2.3 forbids silently swapping in the viable
   form post-hoc. Rung 3 = 0 events → rungs 4–5 have NO sample
   (recorded as a definition failure discovered from inputs only —
   zero outcome data involved), i.e. rung 4 (the playbook's real
   retracement fill) and rung 5 (the never-measured variable
   target) were never evaluated.
3. **Switching to the viable FVG form now is parameter selection.**
   C1's standard three-bar gap (c0.low > c2.high) evaluated forward
   from the touch exists in 847/2,108 (40.2%) NQ and 577/1,719
   (33.6%) GC displacement events — the diagnostic
   (`erlirl_diagnostics.py`) shows a testable form exists, but
   re-defining the gate after seeing which definitions survive is
   exactly what §"no parameter selection" forbids. Not run; noted as
   the obvious design input IF this family is ever re-hypothesized
   prospectively.

## 3. Disposition (governing reading — conservative, per C2 precedent)

**No combination of displacement + fresh FVG + retracement flipped
the sign — the combination sample is EMPTY; the single rung that
flipped is diagnosed as a selection-mechanical artifact (§2.1).**
Per the directive's own kill rule ("if no combination of
displacement, fresh FVG, and retracement flips the sign… the
hypothesis is dead — record it, close it, no pre-registration is
drafted, and the next campaign starts fresh"):

> **ERL→IRL: CLOSED. No Campaign 3 pre-registration drafted.
> Next campaign starts fresh.** The mechanical FLIP line is preserved
> above (no history rewrite of the frozen rule's output); the
> governing reading is DEAD, and the authority for that reading is
> the diagnosis's falsifiable facts: n=0 at every rung that
> constitutes the hypothesis, and 96% continuation-stop rate at the
> one non-empty gated rung — both computed from the frozen run's
> artifacts.

Both §0 cases were recorded honestly before this: the friction
argument (0.035–0.140R vs 0.2R floor) was real and remains the
program's standing arithmetic for any future 30m hypothesis; the
prior against it (C2 sweep continuation −0.1846R; C1 gates minus
17.4% vs 34.9%) is now extended by one more transferable lesson —
**an ablation rung that conditions its stamp on the move it then
scores, with a payoff frame whose stop sits inside that move, is
guaranteed to "flip" on any data.** If the gate family is ever
re-hypothesized, the honest design enters at the displacement close
with symmetric risk, defines the void in the standard three-bar
form BEFORE looking, and keeps the sweep-only baseline as the only
valid frame for measuring the level-entry product.

## 4. Descriptive residual (no inference claimed)

- Rung 2 event-mean tc sensitivity: +1.0434 NQ / +0.6690 GC — same
  artifact under the alternative entry convention.
- Median touch-bar range is 42.25 pts NQ (≈2.96× ATR): first-touch
  bars at overnight extremes are large bars; any future void design
  must size gaps relative to the sweep bar, not to ATR.
- The one genuinely open, unpriced question this pass leaves is not
  "does the chain reverse" (the chain never formed) but the
  continuation-after-displacement momentum reading implied by §2.1 —
  a CONTINUATION hypothesis, the opposite of ERL→IRL's premise, and
  outside any claim of this record.

## 5. Artifacts

`erlirl_ablation.py` (ladder, pure-prefix gates),
`erlirl_ablation.json` / `_report.txt` (frozen-run output),
`erlirl_diagnostics.py` / `.json` (validity numbers in §2),
`test_erlirl_ablation_lookahead.py` (permanent, 14 tests).
`data/databento/erlirl_bars_*.pkl` bar caches live in the git-ignored
dir. No ledger file was modified; committed C2 artifacts untouched.
