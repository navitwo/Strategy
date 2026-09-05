# C3-ABSORPTION-PROXY — Gate A cost result and final verdict

Date: 2026-09-05. Protocol: `C3_ABSORPTION_PROXY_PROTOCOL.md`, frozen
and committed (`19398ed`) BEFORE any quote number existed. Character:
exploratory; zero promotion power; no Campaign 3 pre-registration
drafted in this pass, in either branch.

## 1. Gate A — free `metadata.get_cost` quotes (nothing purchased, nothing downloaded)

All GLBX.MDP3, `stype_in=continuous`, 2010-06-07 → 2026-09-04 (end
exclusive), end date inside the vendor's live boundary:

| # | request | quote |
|---|---|---|
| 1 | NQ.n.0 `trades` full range | **$1,254.8728** |
| 2 | NQ.n.0 `mbp-10` full range | **$4,038.8888** |
| 3 | ES.n.0 `trades` full range | **$1,939.5232** |
| 4 | ES.n.0 `mbp-10` full range | **$4,036.0310** |
| 5a | NQ.n.0 `trades`, conditional windows | **$272.4014** |
| 5b | NQ.n.0 `mbp-10`, conditional windows | **$780.5778** |

Item 5 is the exact sum of 2×2,611 per-window `metadata.get_cost`
calls over the merged ±60-minute windows around all 3,033 committed
NQ events (`nq_event_windows.json`; 5,606.5 total hours = 3.94% of the
full span in time, but 21.7% of the full-range trades cost — the
windows sit in the most liquid hours, and displacement-per-
liquidity is what the absorption metric itself keys on). Two
transient network failures in the first pass were re-quoted and added
(+$0.1993 trades, +$0.4601 mbp-10), so 5a/5b are the complete sums.

**Against the inferred balance $86.6398** (portal-verified $124.68 at
2026-09-04 minus the $38.0402 C2 charge; no Databento balance endpoint
exists, so treat as inferred per DATABENTO_BUDGET.md rule 1):

- conditional trades: **3.14× the entire balance** — and 6.8× the
  protocol's frozen $40.00 ceiling;
- conditional mbp-10: **9.0× the balance**;
- full-history mbp-10 (the level at which the strategy's actual
  mechanism — bid reload — is even observable): **46.6× the balance**.

The cost gap is the headline: shrinking the request from 16 years of
24×7 to exactly the event-hour neighborhoods of the 3,033 events cuts
trades cost by ~4.6× and mbp-10 cost by ~5.2× — and it is *still*
3–9× more than the account can pay. There is no affordable slice of
order-flow data at this event count.

## 2. Gate B decision (mechanical, from the frozen rule)

Protocol §2: purchase only if conditional trades ≤ $40.00 ceiling and
portal re-verification passes. $272.40 > $40.00 → **no purchase of any
kind was made, and none is proposed.** The $86.64 reservation for a
possible ES/YM/RTY index-complex pull is untouched.

## 3. Verdict per protocol §6: DEAD-UNTESTED — CLOSED

> **Order-Flow Absorption & Reload Reversal: UNTESTED-AT-AFFORDABLE-
> COST — CLOSED.** The single falsifiable core claim cannot be probed
> even at proxy resolution (trades-based efficiency on the existing
> event population) within the account's declared ceiling; the
> mechanism-faithful version (mbp-10) is an order of magnitude further
> out again. Per the standing decision discipline, an unfalsifiable-
> because-unaffordable claim is filed dead, with these six quotes as
> the evidence for the filing. No order-book pipeline is built, no
> MBP-10 scope is requested, no Campaign 3 pre-registration is drafted
> for this strategy.

Supporting priors that made the gamble unattractive even before the
quote (both declared in the protocol): (i) the strategy's own worked
example carries ~0.25–0.50R friction on 2–4-point NQ stops — two to
three times the ~0.2R floor that killed Campaigns 1 and 2 — requiring
≈50% win rate at a 2R target just to break even; (ii) its trigger
levels are literally Campaign 2's event, whose corrected NQ Primary A
result is −0.1846R continuation over 3,033 events, so the absorption
filter had to select a subset reversing hard enough to overcome both
that drift and the double cost floor.

## 4. If a future account ever wants this question answered anyway

The pre-written analysis (`c3_proxy_analysis.py`, unexecuted — no
purchase, so nothing to analyze) and this protocol's §3–§5 (frozen,
outcomes-blind split rule and decision thresholds) would make a
re-run mechanical: same windows, same rule, same branching authority;
only the ceiling in §2 and the balance in §1 would change. The event
population's `fwd_R` outcomes remain committed and usable without any
new outcome computation. Re-quote first: Databento prices drift as
the end date rolls.

## 5. Friction caveat the user directive requires stated plainly

Even a positive proxy result would face ~0.5R friction at the
strategy's stated 2-point stop sizes (and ~0.25R at 4-point) — far
above the 0.2R floor that closed both prior campaigns; seconds-scale
backtests are least reliable precisely where queue position and
fast-market slippage dominate; therefore any eventual implementation
must widen the stop or lengthen the hold to bring friction back under
control. With the DEAD-UNTESTED filing, this caveat is moot — the
hypothesis never got far enough to deserve it.
