# Sample report — one wallet, 96 launches across three days

**Case 01 (public preview)** · Analysis 2026-11-16, updated 2026-11-20
Network: Solana mainnet-beta · Method: public RPC only

This is the unedited opening of a real report. The paid version adds the full
token table, funding-chain depth, payout reconstruction and a reproducibility
appendix.

---

## Scope

| Item | Value |
|---|---|
| Subject | one deployer wallet and its upstream funder |
| Data | public Solana RPC (`getSignaturesForAddress`, `getTransaction`, `getTokenAccountsByOwner`) + DexScreener public API |
| Personal data | none. No natural person is identified, no social account is asserted |
| Intent | not asserted. The report lists what the chain records |
| Tool | [solana-launch-forensics](https://github.com/tdkrHuang/solana-launch-forensics) — MIT, standard library only |

Every claim below maps to a transaction signature.

---

## Summary

One wallet created **84 pump.fun tokens on 2026-11-16** in two bursts, then
exited every position. On **2026-11-19 it created 12 more in 14 minutes**. Two
findings are provable rather than inferred:

1. **A single transaction sweeps creator fees from 7 tokens at once**
   (`SweepCreatorFee ×7`). Only a token's own creator can sweep its fees, so one
   wallet holds the creator right on all seven. That is an on-chain entitlement,
   not a timing correlation.

2. **Nine transactions each pay exactly 486,609,148 lamports
   (0.486609148 SOL) to a different fresh wallet**, including transactions that
   also launch a token. A fixed 18-digit amount repeated nine times is software.

---

## 1. Creation cadence

| Burst | Window (UTC) | Tokens | Density |
|---|---|---|---|
| 1 | 2026-11-16 04:49:29 → 05:29:18 | 14 | one every 2m 51s |
| 2 | 2026-11-16 11:30:20 → 12:38:44 | 70 | **68 in 42m 36s** — one every 38s |
| 3 | 2026-11-19 07:35:23 → 07:49:39 | 12 | one every 1m 11s |

Burst 3 was not in the original report. It was found on 2026-11-20 by scanning
the wallet's newest 40 transactions: 12 creations, one mint per transaction,
same fee payer.

Excerpt from the token table (each row verified individually: the oldest
signature touching the mint has the mint as a signer, and the fee payer is the
deployer):

| # | Time (UTC) | Mint | Creation tx |
|---|---|---|---|
| 01 | 11-16 04:49:29 | EGX8MJT8…pump | 5WSkEpd3…Cd8v |
| 02 | 11-16 04:50:15 | 2ZZhunwt…pump | 6qYgkw55…eX38 |
| 03 | 11-16 04:53:10 | 2GoDADTF…pump | RbA2Qtb6…6HaB |
| … | | 93 more rows in the paid report | |

Authorities: `mintAuthority = null` and `freezeAuthority = null` on all 14 in
burst 1. Positions remaining at the 11-16 snapshot: **0 of 14**.

---

## 2. The sweep that turns correlation into proof

```
TX        zWcwg1pBsstXjKUw…whEq
SLOT      470014561
TIME      2026-11-16 05:29:41 UTC
FEE       32,283 lamports
SIGNERS   exactly 1
OPS       SweepCreatorFee ×7, CollectCreatorFeeV2 ×1
MINTS     7 distinct pump.fun mints
CREATES   0
```

A naive parser reports "7 creations in one transaction". That is wrong, and a
reviewer will catch it. The correct reading is stronger: **seven tokens in one
sweep proves one wallet controls all seven creator-fee accounts.**

Verified again on 2026-11-20 with the tool in this repository; the output above
is the current output, not a stored screenshot.

A second sweep in the same window covers 5 more mints — 11 distinct mints, one
signer, both inside the 40-minute creation window.

---

## 3. Where the SOL went

Within a 150-transaction sample, the deployer pays the identical amount to nine
different fresh addresses:

```
0.486609148 SOL × 9 destinations (9 txs)
  -> 3EyicXms…EhPb
  -> 6NmwtSZ5…M2N
  -> 8yyhHiGQ…WobS
  -> ARq9u3Rr…YV5Q
  -> BGdigCjK…j8GD
  -> FRFoYWbU…xYVA
  -> 2c5o9kpr…vJq4
  -> 6yXMhhR4…rYfa
  -> joxY6Kr3…nNo
```

The same amount is paid **inside** transactions that also launch a token:

```
TX    56TLyKD4R8Tn…SKHV
OPS   CreateV2, BuyV2
MINT  3j7DSrqg…pump
OUT   0.486609148 SOL -> 3EyicXms…
BACK  0.001459828 SOL -> funder
```

Fixed lamports per launch, to a fresh address each time, is a fee split executed
by software.

---

## 4. Verify it yourself

```bash
git clone https://github.com/tdkrHuang/solana-launch-forensics
cd solana-launch-forensics

python3 -m launchforensics tx    zWcwg1pBsstXjKUw3oEZrqz4hpsYd5CCkY5kvksTHFJBDhipaYH97CqgQtnApERa9eBziPKYkdN3hWYCJ44whEq
python3 -m launchforensics scan  <DEPLOYER> --limit 400
python3 -m launchforensics flows <DEPLOYER> --min-sol 0.4 --across-tx
```

Python 3.9+. No API key, no wallet connection, no crypto SDKs. If the default
public RPC is slow, pass `--rpc https://api.mainnet-beta.solana.com`.

---

## 5. Limits (stated in the report, not hidden)

- Documents mass creation and rapid full exit. Does **not** assert intent,
  coordination with third parties, or harm to any identified person.
- Outflow aggregates cover a 120–150 transaction sample, not the wallet's
  lifetime.
- Burst 3 was found in the newest 40 transactions on 2026-11-20; older activity
  between 11-16 and 11-19 was not scanned.
- Prices are a snapshot and move.
- Batched creation and repeated payouts are **patterns**, not a verdict.

---

## What the paid version adds

| Lite $99 | Standard $299 | Deep $699 |
|---|---|---|
| full token table, every signature | yes | yes |
| funding chain, 1 level | 3 levels + linked wallets with evidence | 15 wallets + past cases |
| payout reconstruction | yes + timeline | yes + statistical cadence |
| authorities / remaining position | yes | yes |
| — | 6–10 page PDF | legal appendix + 30-min call |

Contact: DM [@tdkr_Huang](https://x.com/tdkr_Huang) or open an issue on the repo.
Payment in USDC (Solana) or JPY bank transfer. No personal data is collected
beyond a contact address.
