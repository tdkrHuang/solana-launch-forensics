# solana-launch-forensics

Read-only forensics for pump.fun style token launches. **Standard library only** — no
API key, no `pip install` of crypto SDKs, no wallet connection.

It answers three questions from public chain data alone:

1. **Which mints did a wallet create?**
2. **How fast, and did any share a transaction?**
3. **How did the SOL leave, and did the payouts repeat one size?**

Every output line is traceable to a signature you can paste into an explorer.
The tool never guesses intent.

```
$ launchforensics scan GtTg74Zp…4W14 --limit 60
wallet          GtTg74Zp…4W14
scanned         60 transactions
creations       13
window          9m 11s

created (UTC)        batch  mint                                            tx
2026-11-16 12:22:27      1  C53a9Fc6…pump    ggoZiaudL3jx..6tiw
2026-11-16 12:23:07      1  CqAjDktv…pump    5BHGkpzjtjUU..RLY3
...
```

---

## Install

```bash
git clone https://github.com/<you>/solana-launch-forensics
cd solana-launch-forensics
python3 -m launchforensics --help
```

Python 3.9+. Nothing to install.

Optionally, as a command:

```bash
pip install -e .
launchforensics --help
```

---

## Commands

### `scan <wallet>` — mints created by a wallet

```bash
launchforensics scan <WALLET> --limit 400 --out wallet.json
```

| Flag | Meaning |
|---|---|
| `--limit N` | transactions to inspect (max 1000, newest first) |
| `--out FILE` | write the full JSON result |
| `--json` | print JSON to stdout |

Reports `creations`, the time `window` between the first and last creation, and any
transaction that created more than one mint.

### `tx <signature>` — one transaction, decoded

```bash
launchforensics tx <SIGNATURE>
```

Resolves which program emitted each `Program log:` line by walking the
`invoke` / `success` stack, so pump.fun operations are counted separately from
token-program noise. Output includes signers, fee, pump instruction counts,
referenced mints, SOL transfers and repeated equal-size outflows.

### `flows <wallet>` — repeated equal-size payouts

```bash
launchforensics flows <WALLET> --limit 200 --min-sol 0.01 --across-tx
```

Groups SOL transfers leaving the wallet by exact lamport amount. Scripted splitters
tend to pay one number to many destinations; humans rarely do.

| Flag | Meaning |
|---|---|
| `--across-tx` | group identical amounts **across** transactions (default: within one tx) |
| `--min-count N` | minimum distinct destinations to report |
| `--min-sol X` | ignore dust below X SOL |

Real output — nine wallets received the identical 486,609,148 lamports:

```
$ launchforensics flows GtTg74Zp… --limit 150 --min-sol 0.4 --across-tx
0.486609148 SOL x 9 destinations  (9 txs)
  -> 2c5o9kpr…vJq4
  -> 3EyicXms…hPb
  -> 6NmwtSZ5…M2N
  ...
```

`--across-tx` is the mode that matters for payout analysis: a splitter usually pays
one destination per transaction, so a within-transaction view finds nothing.

---

## What it correctly distinguishes

Two traps that produce wrong conclusions:

**1. `Program log:` lines carry no program id.**

A pump.fun `CreateV2` fans out into Token-2022, which logs its own
`Instruction: InitializeMint2`. Naive substring counting reports two creations per
launch. This tool attributes logs through the invoke stack, so `create_count`
returns `1`.

**2. Touching a mint is not creating it.**

A creator-fee sweep references seven mints and contains zero creations:

```
$ launchforensics tx zWcwg1pBsstXjKUw…whEq
pump ops    SweepCreatorFee x7, CollectCreatorFeeV2
creates     0
mints       7 referenced
```

That distinction matters: a sweep across seven mints proves one wallet controls the
creator-fee accounts of all seven. Calling it "seven launches in one transaction"
would be wrong, and a reviewer will check.

---

## Output schema

`scan` writes:

```json
{
  "wallet": "...",
  "scanned_transactions": 400,
  "creation_count": 27,
  "window_seconds": 2350,
  "creations": [
    {
      "mint": "...pump",
      "signature": "...",
      "slot": 470014561,
      "block_time": 1763268569,
      "batch_size": 1
    }
  ],
  "batch_transactions": []
}
```

---

## Limits, stated plainly

- **Public RPC is rate limited.** Default pause is 0.35 s and requests retry with
  backoff. `scan` skips individual failed transactions and reports
  `failed_transactions` instead of aborting. If you see many failures, switch
  endpoint:

  ```bash
  launchforensics --rpc https://solana-rpc.publicnode.com scan <WALLET> --limit 400
  ```

  For serious volume, point `--rpc` (or `SOLANA_RPC_URL`) at your own node.
- **`--limit` caps history.** `scan` reads newest-first; a wallet older than the
  window will appear to have fewer creations. Results say `scanned_transactions`
  so the bound is visible.
- **pump.fun mints are detected by the `pump` suffix.** Non-pump SPL mints are only
  found when the RPC returns parsed `initializeMint` instructions.
- **No price or PnL data.** Deliberately. Prices come from third-party APIs with
  their own reliability; this tool only reports what the chain itself records.
- **Not a verdict.** Repeated equal-size payouts and batched creations are patterns,
  not proof of wrongdoing.

---

## Tests

```bash
python3 -m pytest -q
```

Fixtures in `tests/fixtures.py` mirror real responses, including a versioned
transaction **without `message.header`** and a Token-2022 `InitializeMint2` nested
inside a pump.fun call.

---

## License

MIT
