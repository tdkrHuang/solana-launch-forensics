# Sample report — one wallet, 14 launches in 40 minutes

**Case 01 (public preview)** · Analysis 2026-11-16, updated 2026-11-20
Network: Solana mainnet-beta · Method: public RPC only

> **Rebuilt, 2026-11-26.** The first preview said 84 tokens in two bursts. That
> count came from an attribution bug: every pump mint in a transaction was
> credited to its fee payer, including mints the wallet only bought. The verified
> burst is 14 tokens, each with an `InitializeMint` instruction in a transaction
> the wallet paid for.

This is the unedited opening of a real report. The paid version adds the full
token table, funding-chain depth, payout reconstruction and a reproducibility
appendix.

You can reproduce the created / swept edges yourself in the
[browser demo](https://tdkrhuang.github.io/solana-launch-forensics/demo/) — paste any wallet,
no install or API key.

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

One wallet created **14 pump.fun tokens on 2026-11-16**, between 04:49:29 and
05:29:18 UTC, then exited every position. Two findings are provable rather than
inferred:

1. **A single transaction collects the creator fee of 7 tokens at once**
   (`SweepCreatorFee ×7`), and all seven are among the 14 the same wallet had
   just created. Collection is permissionless — any signer can submit it — so the
   sweep is corroboration of the creation list, not a substitute for it. Both
   halves are shown with signatures.

2. **Nine transactions each pay exactly 486,609,148 lamports
   (0.486609148 SOL) to a different fresh wallet**, including transactions that
   also launch a token. A fixed 18-digit amount repeated nine times is software.

---

## 1. Creation cadence

| Burst | Window (UTC) | Tokens | Density |
|---|---|---|---|
| 1 | 2026-11-16 04:49:29 → 05:29:18 | 14 | one every 2m 51s |

Every row is a transaction whose fee payer is the deployer and which contains a
token-program `InitializeMint` for that mint. A fifteenth mint created in the
same window (`B4Dck7qQ…pump`, 05:20:23) had a different fee payer and is
excluded.

Excerpt from the token table (each row verified individually: the oldest
signature touching the mint has the mint as a signer, and the fee payer is the
deployer):

| # | Time (UTC) | Mint | Creation tx |
|---|---|---|---|
| 01 | 11-16 04:49:29 | EGX8MJT8…pump | 5WSkEpd3…Cd8v |
| 02 | 11-16 04:50:15 | 2ZZhunwt…pump | 6qYgkw55…eX38 |
| 03 | 11-16 04:53:10 | 2GoDADTF…pump | RbA2Qtb6…6HaB |
| … | | 11 more rows in the paid report | |

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
reviewer will catch it. The correct reading is narrower: **one wallet paid to
submit a fee collection for seven mints.** Collection is permissionless, so this
proves payment, not ownership; whether the same wallet created the mints is a
separate question, answered only by the creation transactions.

The seven mints in that transaction are the same seven the wallet created
earlier in the same 40 minutes:

| Mint | Created (UTC) | Creation tx |
|---|---|---|
| 2GoDADTF…pump | 04:53:10 | RbA2Qtb6…6HaB |
| G4fWV2pw…pump | 05:13:21 | 434qsa5D…rLUe |
| GSv8mhfw…pump | 05:14:34 | 54xj2eEU…cnpW |
| BXdB9Zoi…pump | 05:20:07 | 3AjPrdXr…ksv2 |
| 4nAo2vHU…pump | 05:25:08 | 3oQ6FSms…eogY |
| EzVx9uqr…pump | 05:29:03 | 2gYFxjf7…zDi2 |
| 8JHykVcX…pump | 05:29:18 | 2FNVuWTo…EKXb |

This is the check the tool now performs by default: a `swept` link is kept only
when the same wallet also has a `created` link for that mint. Without the
creation table, the sweep would prove only that someone paid to collect.

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

# The 11-16 burst is older than the current 400-transaction window.
# To reproduce it, start from the creation transactions in the table above
# (any one of them resolves the mint and its block time).
```

Python 3.9+. No API key, no wallet connection, no crypto SDKs. If the default
public RPC is slow, pass `--rpc https://api.mainnet-beta.solana.com`.

---

## 5. Limits (stated in the report, not hidden)

- Documents mass creation and rapid full exit. Does **not** assert intent,
  coordination with third parties, or harm to any identified person.
- Outflow aggregates cover a 120–150 transaction sample, not the wallet's
  lifetime.
- The creation table covers the 11-16 burst only. Later activity is outside the
  window used here and is not counted.
- Creations come from the token program's `InitializeMint`; fee collections are
  counted only when the same wallet also created the mint in the same window.
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
