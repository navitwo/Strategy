# Databento Budget — standing cost-control record

This file exists so the account's spend state never has to be manually
re-read for routine work. It is maintained by the same discipline as the
preregistration documents: every number has a source and a date.

## Standing rules (enforced in code, not intent)

1. **The tracked figure below is an INFERRED estimate, not a balance.**
   Databento exposes no balance/credits endpoint (probed 2026-09-04:
   `billing.balance`, `billing`, `billing.charges`, `users.get` all HTTP 404
   on hist/api hosts; official client 0.86.0 offers only
   batch/metadata/symbology/timeseries services). Any local number drifts.
   **Before ANY request estimated above $10, re-verify the balance manually
   from https://databento.com/portal/billing.** Code enforcement:
   `d48_databento_purchase.py` refuses any purchase whose live quote
   exceeds $10 unless the operator sets `DATABENTO_PORTAL_REVERIFIED=1`
   (asserting the portal check was just done), in addition to `CONFIRM=1`.
2. **If inferred and actual diverge by more than $1, STOP and reconcile
   before spending.** The ceiling check in `d48_databento_purchase.py`
   (re-quote immediately before submission, abort above MAX_USD) is the
   in-code enforcement of the same principle for purchases.
3. Credits die on a clock regardless of remaining balance (see expiry
   below) — a healthy inferred balance does NOT imply spendable balance
   after the expiry date. Re-verify after 2027-02-09 before any purchase.

## Account state

| item | value | source |
|---|---|---|
| Portal-verified balance | **$124.68** as of 2026-09-04 | user, billing page |
| New-account credit grant | $125.00 | account terms |
| Credits expire | **2027-02-09** (six months from account creation; creation evidenced by the three sample jobs dated 2026-08-09) | portal + job list |
| Payment method on file | yes — overage becomes a real charge | account terms |

### $0.32 pre-purchase consumption — reconciled

The first `batch.list_jobs` call (2026-09-04) showed exactly three jobs, all
from 2026-08-09, all `XNAS.MDP` sample data (Microsoft: `trades`, `ohlcv-1m`,
`mbo`). These are the account-creation sample pulls and account for the
$125.00 − $124.68 = **$0.32** gap. No unexplained spend remains.

## Spend ledger

| date | request | get_cost quote | actual charge | inferred remaining |
|---|---|---|---|---|
| 2026-08-09 | XNAS sample jobs ×3 (trades/ohlcv-1m/mbo MSFT) | — | $0.32 | $124.68 (portal-verified 2026-09-04) |
| 2026-09-04 | C2 purchase: GLBX.MDP3 ohlcv-1m + definition, NQ.n.0+GC.n.0 continuous, 2010-06-07→2026-09-04 (d48, ceiling $45) | **$38.04** (re-quoted immediately pre-submit) | ohlcv-1m **$38.031821** + definition **$0.008394** (job fields; sum $38.0402 = quote exactly) | **≈ $86.64** |

*Quotes vs actuals: Databento bills the confirmed job cost, which for
batch bulk jobs matches the pre-quote at the same range. If post-purchase
portal reconciliation shows |actual − $38.04| > $1, rule 2 above applies.*

### Purchased container provenance (tracked; the files themselves live under git-ignored data/databento/)

| file | bytes | sha256 |
|---|---|---|
| glbx-mdp3-ohlcv-1m.zip | 156,181,748 | c73fa087a7145d1ccce136042ad03c9cd495692a06a77b9e474dcd5f51d1287f |
| glbx-mdp3-definition.zip | 6,313,758 | 29dfb228a939d60156502f1f0e901891cc1d4df199a7aa38c0beb04334620b08 |

Jobs: ohlcv-1m GLBX-20260904-77GSFBPBNT ($38.031821); definition
GLBX-20260904-YTWSXK7WDK ($0.008394). Both containers are ZIPs of
per-UTC-day .dbn.zst members. Verify after any restore:
`certutil -hashfile data\\databento\\<file> SHA256`.

## Known quotes (context, not commitments)

- Parent symbology `NQ.FUT,GC.FUT` 2010-06-07→2025-01-01: **$71.04**
  (over-pulls every listed month; superseded).
- Continuous `NQ.n.0,GC.n.0` 2010-06-07→2026-09-04: **$38.04** — half the
  cost of the parent pull for twenty months MORE data. Symbology switch
  was the cost decision; re-quotes shift daily as the end date rolls.
- ES/YM/RTY were deliberately NOT included in this purchase (design
  decision deferred, not an accident of the download).
- Guard (c) extension point: the local QC bundle covers gc (comex) and es
  (cme) minutes; the 2013-10 GC weekday block is the live reconciliation
  window. NQ has no local QC coverage — ES rides the same CME-Globex
  consolidation code path and is the designated extension point for the
  index-complex side when needed.
