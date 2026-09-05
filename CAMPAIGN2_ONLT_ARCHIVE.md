# C2-ONLT-v1 — ARCHIVE: CLOSED AS NULL, FILED AS CAMPAIGN 3 HYPOTHESIS GENERATOR

**Status:** C2-ONLT-v1 is **archived on its DEV evidence**. Both primary
verdicts are NULL, the screening labels are `significant_not_tradable` in
both markets, no promotion trigger fired, and validation and holdout data
remain **locked and unread** — this campaign closed without ever opening
them. The confirmatory questions C2 asked are answered; they are not to be
relitigated. This document exists because the raw null understates what the
ledger contains: C2's real output is the seed list for Campaign 3.

Everything numeric here is reproducible offline from the committed
per-event ledger `c2_local_study.json` by `c2_archive_analysis.py`
(output `c2_archive_analysis.json`). The script re-derives each committed
primary CI bit-for-bit with the study's own imported estimator before
computing anything else; if ledger and study ever drift, it fails loudly.
No Databento access, no cloud, no re-decode.

- Protocol: `CAMPAIGN2_OVERNIGHT_LEVEL_TOUCH_PREREGISTRATION.md` (frozen).
- DEV pass: `c2_local_study.py` → `c2_local_study.json` /
  `c2_local_study_report.txt`, permanent ledger tests
  `test_campaign2_ledger.py` (6 green).
- Guards: 22 tests green in `test_databento_local_guards.py` (incl. NQ + GC
  cloud reconciliation, roll windows, date-gate self-audit).
- Commit of record: `68c2fdb` (with `HEAD == origin/main`).
- θ = 0.2R fixed; primary cell T2S0.5 / H120m / pessimistic paired
  reversal−continuation contrast; winsorized (−0.5, +2.0); session-date
  clustered bootstrap.

## 1. The frozen verdicts (unchanged, final)

| | Primary A (NQ) | Primary B (GC) |
|---|---|---|
| contrast (cluster-mean R) | **+0.0536** | **−0.0878** |
| 95% CI | [+0.0052, +0.0997] | [−0.1226, −0.0532] |
| confirmatory (θ=0.2R) | **NULL** | **NULL** |
| screening vs zero | significant_not_tradable | significant_not_tradable |
| n / sessions | 3,033 / 2,570 | 2,468 / 2,370 |

Direction convention: positive = reversal, negative = continuation.
Both CIs exclude zero but sit far inside ±0.2R: each market shows a real,
precise, **sub-threshold** effect. §7 promotion trigger: not fired. No
random-time control is owed. The verdicts stand as filed.

## 2. Four things the bare null understates

### 2.1 The A/B split was load-bearing — pooling would have manufactured a nothing

NQ's effect is **+0.054R (reversal)**; GC's is **−0.088R
(continuation)** — opposite directions, each significant within its own
CI. The pooled equal-market mean is **−0.017R**, indistinguishable from
zero: the two real effects arithmetically cancel. Under the originally
frozen single-primary design (NQ+GC pooled as one index-and-gold "regime
panel"), this study would have reported a flat null with no signal at all
and the archive would contain nothing. The pre-data amendment splitting
Primary A (NQ) and Primary B (GC) *was* the difference between a result and
a non-result — and it was made on methodology grounds before any DEV data
was seen, so the finding gets full credit.

**Recorded lesson for Campaign 3 design:** never pool across venues whose
microstructure can carry opposite signs. Two markets is at least two tests.

### 2.2 NQ's effect does not survive realistic entry; GC's does

Same contrast re-resolved under the two declared entry/ambiguity
sensitivity conventions (event-mean R; the JSON carries the clustered CIs
too):

| specification | NQ | GC |
|---|---|---|
| primary (level fill, pessimistic) | **+0.0536** | **−0.0878** |
| optimistic (target-first ambiguity) | +0.0148 | −0.1449 |
| touch_close (entry at touch-bar close) | **−0.0208** | −0.1311 |

NQ's reversal edge exists *only* with a fill exactly at the overnight
level — relax the ambiguity assumption and it nearly halves; move entry to
the touch-bar close and it **flips sign**. That is the signature of an
adverse-selection artifact: the fills that "work" are precisely the ones
Campaign 1 (RTC1/RTC2) demonstrated a live trader cannot get — the touch
that becomes a reversal is the touch that keeps going through a resting
level order. GC, by contrast, holds the **same sign and similar magnitude
across all three specifications** (−0.09 / −0.14 / −0.13, all clustered
CIs excluding zero on the same side). Both remain below θ=0.2R — the
NULLs are unchanged — but this is a materially different *quality* of
evidence between the two markets and belongs on the record.

**Recorded lesson:** the direction of robustness is GC. If any C2
observation deserves a second campaign, it is the gold continuation
signal, not the NQ reversal signal.

### 2.3 EXPLORATORY — the horizon profiles are opposite

The ledger carries signed forward returns at 30/60/120/240 minutes.
Event-mean point, session-clustered bootstrap CI (4,000 draws), sign as
above. **Eight post-hoc comparisons made after seeing the data:**

| horizon | NQ | GC |
|---|---|---|
| 30m | −0.079 [−0.162, +0.002] ns | **−0.096 [−0.155, −0.037] cont-SIG** |
| 60m | −0.063 ns | **−0.076 [−0.148, −0.008] cont-SIG** |
| 120m | −0.070 ns | −0.052 ns |
| 240m | **−0.161 [−0.296, −0.027] cont-SIG** | −0.047 ns |

**GC is a short-horizon continuation effect**: significant at 30m and 60m,
decaying to non-significance by 120m/240m. **NQ shows nothing at short
holds** — its only significant horizon is 240m, and it is *continuation*,
opposite in sign to its own 120m barrier contrast (which is reversal).
The same event population reads differently across the horizon axis;
these two profiles cannot both be the shape of one phenomenon.

With eight comparisons, one or two clearing 95% by chance is unremarkable.
The GC pattern is at least internally coherent (adjacent horizons, same
sign, monotonically decaying — the shape a real short-horizon continuation
would have), while NQ's lone 240m cell has no neighbouring support. Still:
**lead, not finding.** No promotion power; cannot change any C2 verdict.

### 2.4 EXPLORATORY — at 120m the effect lives entirely in overnight-high touches

Splitting the same statistic by which level was touched (four more
post-hoc comparisons):

| | overnight-high touches | overnight-low touches |
|---|---|---|
| NQ fwd 120m | **−0.151** [−0.322, +0.021] | +0.018 ns |
| GC fwd 120m | **−0.125** [−0.248, −0.013] SIG | +0.024 ns |

At 120m, **overnight-high touches carry the entire (continuation-direction)
effect in both markets while overnight-low touches are flat**. The barrier
contrast (rev−cont, pessimistic) tells a subtler version of the same
story: NQ-high +0.199 SIG-reversal / NQ-low −0.050 ns; GC-high −0.061
SIG-cont / GC-low −0.100 SIG-cont (the GC-low barrier cell survives, but
its fwd_R mirror is flat — the two statistics disagree, which is itself a
caution against reading structure into this table). Seed-robustness sweep
(25 bootstrap seeds per cell) reports every significant cell significant
at share 1.0 and every null cell at 0.0, so none of these are knife-edge
bootstrap artifacts — but bootstrap stability is not out-of-sample
validity.

**The merged shape of 2.2–2.4, stated as a lead:** *gold continuation after
an overnight-high touch, strongest at short holds, robust to entry
convention.* That is the C2 residue worth a campaign. It is derived
entirely from post-hoc cuts of DEV data, so its prior is unpriced, and
Campaign 3 must test it where C2's own validation windows cannot leak.

## 3. Not tradable — the NULLs stand and are not to be relitigated

No number in §2 changes §1. Best case in the exploratory table is GC at
roughly **0.13 R per unit risked against ~0.2 R of round-trip friction**
(Campaign 1's measured cost floor): even if every exploratory cell
replicated perfectly out of sample, a fixed-barrier 30-minute implementation
still pays less than it costs to trade. The archive says this plainly
because "significant" and "interesting" both invite the wrong inference.
θ was frozen at 0.2R precisely so that sub-threshold effects could be
filed, not fussed over. What §2 licenses is a *new, cheaper, honest test*
of a narrower question — not a re-run of this one.

## 4. Constraints inherited by any successor (hard-won, non-negotiable)

1. **No drop to 3-minute or 5-minute bars.** "Short horizon" means a
   shorter hold on the same 30-minute bars — Campaign 1 established that
   at 5m structures ~0.2R friction dominates before any signal can pay.
   If anything the evidence points toward *larger* bars and *wider* stops,
   which makes friction a smaller fraction of R.
2. **A wider stop is the design lever, not a lower θ.** Any successor
   keeps θ=0.2R-or-above tradability discipline; the way to make 0.13R of
   effect visible against 0.2R of cost is to raise R (wider stop ⇒ fewer,
   larger units of risk per trade) or exit on time rather than a fixed
   barrier — decided in the pre-registration, never tuned on data.
3. **Replication venue must not be GC's own locked windows.** GC-derived
   hypotheses cannot be tested on GC 2025–2026 (validation/holdout stay
   sealed for GC's frozen protocol). Related metals — SI (silver),
   PL (platinum), HG (copper) — are the clean venue: same exchange
   family, same overnight-structure mechanics, untouched data.
4. **Feasibility before everything.** Per the PROTOCOL anchoring rule:
   the successor's power analysis must be anchored to committed ledgers
   (the dispersion anchors from C2 are already re-frozen) or declare
   assumptions with sensitivity ranges. Cost quotes are free; data
   purchase requires portal re-verification per `DATABENTO_BUDGET.md`
   rule 1 and a stated ceiling.
5. **Candidate direction as of archival (exploratory-derived, therefore
   NOT frozen, pre-registration deliberately not drafted):** GC-continuation
   at short holds on overnight-high touches, wider stop so friction is a
   smaller fraction of R, possibly time-based rather than fixed-barrier
   exit. Freezing this before the replication venue is confirmed
   affordable would be freezing on sand.

## 5. Cost posture for the replication venue (quoted, NOT purchased)

Free `metadata.get_cost` quotes, 2026-09-04, GLBX.MDP3,
`ohlcv-1m + definition`, continuous front-month `SI.n.0, PL.n.0, HG.n.0`,
2010-06-07 → 2026-09-04 (exclusive end; the vendor's live-data boundary
rejects any end past 2026-09-04T17:41Z, same constraint the NQ/GC purchase
hit). Quoted per-symbol and jointly; identical totals (no cross-symbol
discount at this tier):

| symbol | ohlcv-1m | definition | total |
|---|---|---|---|
| SI.n.0 (silver) | $18.7668 | $0.0042 | $18.7710 |
| PL.n.0 (platinum) | $14.8578 | $0.0042 | $14.8620 |
| HG.n.0 (copper) | $18.5745 | $0.0042 | $18.5787 |
| **all three jointly** | $52.1990 | $0.0126 | **$52.2116** |

Against the inferred post-purchase balance **$86.6398**
(NQ+GC billing $38.0402 on $124.68 portal-verified), a full three-metal
replication venue would leave **≈ $34.43** margin. Credits expire
2027-02-09. **Nothing purchased.** Per `DATABENTO_BUDGET.md` rule 1,
*any* purchase requires portal re-verification of the live balance and an
explicitly stated ceiling; quote-accuracy tolerance (> $1 drift ⇒ stop)
applies unchanged.

The venue decision (all three, or a cheaper subset) belongs to Campaign 3
protocol design, not to this archive — but it is now cheap-adjacent enough
to decide rationally rather than hopefully.

## 6. What C2-ONLT-v1 is, in one line

A pre-registered overnight-level-touch event study that found two real,
significant, sub-threshold, opposite-signed market-specific effects it was
never allowed to trade — and, in the residue, a coherent gold-continuation
shape that a better-designed successor can test once, honestly, on metal
C2 never touched.

*Archived 2026-09-04 at `68c2fdb`+archive. θ=0.2R stands. Validation and
holdout remain locked and unread. No optimization, no parameter selection,
no second look at DEV.*
