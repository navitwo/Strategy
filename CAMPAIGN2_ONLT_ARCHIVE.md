# C2-ONLT-v1 — ARCHIVE: CLOSED (post-fix verdicts; residue probed DEAD)

**Status:** C2-ONLT-v1 is **archived and closed** on its DEV evidence as
re-executed 2026-09-05 after a resolver-defect fix (§0). GC primary NULL;
NQ primary INCONCLUSIVE; no promotion trigger under prereg §7; validation
and holdout remain **locked and unread** — never opened. The
stop-widening feasibility probe pre-committed at `fb6fe63` returned
**DEAD** under its frozen rule (§4): the gold residue does not survive a
wider stop even at its best-case upper bound. **The residue is closed.
The next campaign starts from a fresh hypothesis**, not from C2's remains.

Every number is reproducible offline from the committed ledger
`c2_local_study.json`: primary/verdict figures by `c2_local_study.py`
(fixed resolver, frozen seeds), archive figures by
`c2_archive_analysis.py`, probe figures by `c2_residue_stopwiden.py`
(frozen protocol `C2_RESIDUE_STOPWIDEN_PROTOCOL.md`, rule committed
BEFORE results existed). Permanent tests: `test_resolve_arm_semantics.py`
(8), `test_campaign2_ledger.py` (7), `test_campaign2_archive.py` (6).

- θ = 0.2R fixed, never widened; primary cell T2S0.5 / H120m /
  pessimistic paired reversal−continuation contrast.
- Commit lineage: defect found during archive work (2026-09-04/05);
  rule committed `fb6fe63`; corrective re-execution follows in this
  commit's history. No history was rewritten.

## 0. Defect disclosure (the honest headline of this archive)

The stop-widening probe's own soundness gate — "the stored bar-path
contrast must lie inside the window-extremes bracket" — failed loudly on
first execution, and tracing it to root cause found an **inverted stop
condition in the local resolver** (`c2_local_study.resolve_arm` and its
companion extremes loop): adverse price movement was recorded positive
while the stop test demanded `adv <= -s_R`. Consequences: the frozen
0.5R stop could never fire on genuine adverse moves, and a "stop" paid
out when price ran 0.5R+ entirely to the profit side. The stored
`reversal_R`, `continuation_R`, `contrast_R`, both sensitivity contrasts,
and `mae_R` — every barrier payoff — were priced under this inversion.
Campaign 1's hosted resolver (the frozen reference, `scifvg_main.py:481`
/ `random_time_control.py:1326`) records adverse negative and was always
correct; the C2 local port diverged from it.

Fix, verification, and scope: corrected to C1 parity; pinned by 8
synthetic RED→GREEN regression tests (`test_resolve_arm_semantics.py`);
the soundness gate promoted to a permanent ledger test
(`test_payoffs_consistent_with_recorded_extremes`); the frozen DEV pass
re-executed on identical inputs (event population, funnel, bars, rolls,
`fwd_R`, `mfe_R` verified field-wise IDENTICAL — only barrier payoffs
and `mae_R` moved). Preregistration §8 retains the original record
verbatim with a disclosure header; §8a carries the corrected replay. The
defect touched no protocol text, no gate, no seed, no data window, and
never reached validation/holdout or any purchase decision.

**Why this is the archive's most valuable output:** two independent
verdict-facing figures (the NQ sign, and the pre-fix "opposite-sign
cancellation" story) were artifacts of the inverted stop, and they were
in the wild for less than a day because a self-imposed soundness gate —
built for an unrelated probe, on data already committed — caught them.
A soundness gate that can fail is worth more than any number.

## 1. Corrected frozen verdicts (final)

| | Primary A (NQ) | Primary B (GC) |
|---|---|---|
| contrast (cluster-mean R) | **−0.1846** | **−0.0958** |
| 95% CI | [−0.2494, −0.1194] | [−0.1649, −0.0328] |
| confirmatory (θ=0.2R) | **INCONCLUSIVE** (CI straddles −θ) | **NULL** |
| screening vs zero | significant_beyond_theta | significant_not_tradable |
| n / sessions | 3,033 / 2,570 | 2,468 / 2,370 |

Direction: negative = continuation. Under the corrected stop semantics
**both markets show continuation** at the barrier cell — the pre-fix
"+0.054 reversal in NQ / opposite signs" reading was a defect artifact
and is formally retracted. NQ's straddled CI is INCONCLUSIVE by the
frozen three-outcome geometry: it neither clears θ wholly (no POSITIVE)
nor sits wholly inside (no NULL), and §7's promotion requires a verdict
that is "robust, economically meaningful, and ambiguity-stable" — a
straddle is none of those. GC's NULL is the same label as pre-fix
(point −0.0958 vs −0.0878; the gold result was always small and
continuation-direction). Stand-down gates: n ≥ 800 passes both;
realized sd NQ 1.8703R / GC 1.6145R sits 17%/1% above the anchored
central 1.6015R but far under the 1.5x ceiling — the corrected stop
semantics produce a genuinely fatter two-sided payoff table, disclosed
rather than smoothed. NQ's cluster-vs-event point gap (−0.1846 vs
−0.0229) is disclosed in prereg §8a.

## 2. What survives the fix (recorded with the corrected pins)

### 2.1 Entry-convention robustness (corrected)

Barrier-contrast event means across the three declared specifications
(primary pessimistic / optimistic-ambiguity / touch-close entry):

| specification | NQ | GC |
|---|---|---|
| primary (clustered point) | −0.1846 | −0.0958 |
| optimistic ambiguity (event mean) | −0.0147 | −0.0908 |
| touch-close entry (event mean) | −0.0486 | −0.0648 |

The pre-fix narrative ("NQ flips sign, GC holds") dies with the fix,
but the **quality asymmetry survives in corrected form**: GC's point is
near-identical under all three conventions (−0.096/−0.091/−0.065 — all
clustered CIs exclude zero, continuation, share 1.0 on the seed sweep);
NQ's large clustered primary collapses to ~zero on event means and its
CI straddles θ — NQ remains the fragile market, now for dispersion
reasons rather than sign reasons. The Campaign 1 lesson (exact-level
fills suffer adverse selection) was never tested by this table either
way; it stands on its own evidence.

### 2.2 EXPLORATORY horizon profiles — UNCHANGED (defect-immune)

The horizon table runs on `fwd_R`, whose close-price formula was never
affected; field-wise verification confirmed byte-identity. **GC is a
short-horizon continuation effect** (30m −0.0960 SIG, 60m −0.0762 SIG,
decaying to ns at 120/240m); **NQ shows nothing until 240m** (−0.1611
SIG continuation, no neighbouring support). Still labelled exactly as
before: eight post-hoc comparisons, leads not findings, zero promotion
power, seed-sweep shares 0.0/1.0.

### 2.3 EXPLORATORY touch split at 120m — half survives

The forward-return rows are unchanged (same formula, same values):
GC overnight-high −0.1248 SIG / low +0.0236 ns; NQ high −0.1506 (CI
touching zero) / low +0.0177 ns. The barrier-contrast touch cells,
re-pinned post-fix, tell a less structured story: NQ high −0.1009
(now continuation, like everything else post-fix), NQ low +0.0620 ns;
GC high −0.0610 and GC low −0.0535 — **both GC cells non-significant
after the fix's wider dispersion.** "The effect lives in
overnight-high touches" remains true of the exact forward-close
statistic and no longer of the barrier statistic. Recorded as such.

### 2.4 What died with the fix

1. The "A/B split saved the study from cancellation" story (§2.1 of the
   pre-fix archive): post-fix signs agree; the pooled −0.1402 is the
   average of two same-direction numbers. The split amendment is still
   correct methodology — one market's NULL should never be diluted by
   another's straddle — but its empirical vindication was an artifact
   and the claim is retracted.
2. Any inference that C2 found *reversal* anywhere. It found
   continuation, small.

## 3. The not-tradable arithmetic, corrected

GC NULL is unchanged in kind: |−0.0958R| < θ. NQ's INCONCLUSIVE straddle
is *not* a near-miss POSITIVE — per §7 it licenses nothing, and the
ambiguity sensitivities collapse it toward zero anyway. The exploratory
GC-short-horizon cells run 0.08–0.13R per unit risked against ~0.2R
round-trip friction (Campaign 1's measured floor). Exactly as pre-fix:
**nothing in this study is tradable at θ=0.2R, and the verdicts are not
relitigable.**

## 4. The pre-committed feasibility probe: GC-high, wider stops

Question (from the user directive, 2026-09-05): can a wider stop make
the residue's friction fraction small enough to matter? Rule and method
frozen at `fb6fe63` before results existed (`C2_RESIDUE_STOPWIDEN_
PROTOCOL.md`): family A target fixed 2R, stops 0.5/1.0/1.5/2.0R;
window-extremes payoffs give each cell a valid [lo, hi] bracket over
first-touch orderings (the mfe/mae blindness is precisely the Campaign 1
defect class — every favourable endpoint is an UPPER BOUND, never
evidence); the scaling identity: margin-per-risked = (|c|−0.2)/s', so
wider stops only rescue an effect by *changing the payoff distribution*,
not by arithmetic. Soundness gate (bracket must contain the stored exact
baseline) passed on the corrected ledger — the gate that found §0.

**Family A, GC overnight-high (n=1,263), contrast in ATR points:**

| stop | lo (best case for continuation) | hi (conservative) | degenerate share |
|---|---|---|---|
| 0.5R | **−0.2439** [−0.3353, −0.1453] | +0.1223 [+0.0309, +0.2162] | 86.9% |
| 1.0R | **−0.1869** [−0.3048, −0.0721] | +0.0721 [−0.0451, +0.1900] | 93.0% |
| 1.5R | −0.1683 | +0.0008 | 96.8% |
| 2.0R | −0.1869 | −0.0602 | 98.4% |

**VERDICT UNDER THE FROZEN RULE: DEAD.** The first DEAD clause fired:
even the *most continuation-favourable valid bound* decays toward zero
as the stop widens (−0.244 → −0.187 at 1.0R), and the conservative
reading is sign-inverted (positive) at 0.5–1.5R. No cell on either
bracket end has a CI wholly beyond the 0.2R friction line — the widest
best case, 0.5R/2R, only reaches −0.24 with CI [−0.34, −0.15], straddling
the friction threshold it must clear. The 87–98% degenerate share says
why barrier reasoning from window extremes is so weak here: for most
events the recorded extremes simply don't separate the wider barriers —
the data cannot resolve these cells more finely, and that is itself the
answer to "does a wider stop help": **we cannot make it look like it
helps even with an upper bound, and upper bounds were the best case the
method allows.**

**Time-exit analogue (exact, ordering-free; contrast = 2·fwd at the
GC-high population):** −0.2799 at 30m, −0.2681 at 60m, −0.2496 at 120m,
−0.2889 at 240m — every point magnitude above the 0.2R friction line,
no CI wholly beyond it. Even the one statistic free of the method's
limit fails the conservative test at this n. A pure time exit does not
manufacture margin the effect doesn't already carry, and it doesn't.

NQ overnight-high reported for contrast (frozen rule applied to GC only)
shows the same pattern: best-case bound −0.60/+0.48 bracket at the C2
grid — wider than its effect, sign-ambiguous. The "hold or strengthen
with margin" branch that would have licensed a Campaign 3 pre-registration
on the gold residue **did not fire, and the more conservative reading
governs**.

## 5. Disposition (per the pre-committed rule)

**The residue is dead. Record it, close it, move on.** Campaign 3 — if
and when it comes — starts from a fresh hypothesis, not from C2's gold
continuation. Two legitimate notes for that future drafter, neither a
residue: (a) the corrected C2 result — continuation-direction, GC
robust/NQ fragile under entry conventions, short-horizon decay in GC —
is filed descriptive record and may inform priors, as any published
null does; (b) the soundness-gate discipline of §0 is the transferable
asset and already persists as permanent tests. The prior on this
residue was weak by construction — one market, post-hoc, derived from
12+ after-seeing-data comparisons — and this probe was always a
cheap-offer test of a long-shot, not a resurrection. A fresh hypothesis
remains the default use of the next cycle.

## 6. Constraints inherited by any successor (unchanged, still binding)

1. **No drop to 3m/5m bars** — "short horizon" = shorter hold on 30m
   bars; Campaign 1 measured ~0.2R friction dominating at 5m. The
   evidence still points at larger bars / wider stops, and this probe
   adds that the *continuation* residue specifically fails that test.
2. **Replication-venue budget:** SI/PL/HG quoted $52.2116 and
   **declined by user decision** — the inferred ≈$86.64 is reserved for
   a possible index-complex pull (ES/YM/RTY) if a later hypothesis
   warrants it; credits expire 2027-02-09 regardless of balance
   (`DATABENTO_BUDGET.md`, rule 1: portal re-verification + stated
   ceiling before any purchase).
3. **Feasibility anchoring** (PROTOCOL rule) and **exact first-touch
   grids** for any barrier-geometry study: this probe showed from the
   inside why window-extreme shortcuts cannot price wider barriers.
4. **A/B never pooled for confirmatory verdicts** — still correct
   methodology on design grounds, even though its pre-fix empirical
   vindication is retracted.

## 7. C2-ONLT-v1 in one line

A pre-registered event study that found one small, real, robust,
not-tradable continuation effect in gold and an inconclusive straddle in
NQ — and whose greatest contribution was the soundness gate that caught
its own resolver bug before any of it leaked into a decision, then
answered its own final follow-up question ("could it ever be tradable?")
with a pre-committed, upper-bound-generous DEAD.

*Archived 2026-09-05, corrected re-execution. θ=0.2R stands. Validation
and holdout locked and unread, now and forever under this protocol. No
optimization, no parameter selection, no second look.*
