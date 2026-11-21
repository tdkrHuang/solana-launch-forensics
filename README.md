# solana-launch-forensics

[![PyPI](https://img.shields.io/pypi/v/solana-launch-forensics)](https://pypi.org/project/solana-launch-forensics/)
[![CI](https://github.com/tdkrHuang/solana-launch-forensics/actions/workflows/ci.yml/badge.svg)](https://github.com/tdkrHuang/solana-launch-forensics/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Read-only forensics for pump.fun style token launches. **Standard library only** — no
API key, no `pip install` of crypto SDKs, no wallet connection.

It answers four questions from public chain data alone:

1. **Which mints did a wallet create?**
2. **How fast, and did any share a transaction?**
3. **How did the SOL leave, and did the payouts repeat one size?**
4. **Which mints belong to the same operator, and what is the evidence?**

Every output line is traceable to a signature you can paste into an explorer.
The tool never guesses intent.

**Try it without installing anything:** paste a wallet into the
[browser demo](https://tdkrhuang.github.io/solana-launch-forensics/demo/) and get the same
created / swept / funded edges as the CLI. No API key, no wallet connection, nothing
uploaded — the page talks to a public RPC and renders the result.

There is also a [sample report](https://tdkrhuang.github.io/solana-launch-forensics/sample-report.html)
showing what the paid write-up looks like.

## Writing

- [A fee sweep is not a creation](https://dev.to/tdkrhuang/reading-solana-launch-logs-correctly-a-fee-sweep-is-not-a-creation-4gf4) — the two events, and why attribution needs the invoke stack
- [One wallet, 108 launches in 9 hours](https://dev.to/tdkrhuang/one-wallet-108-launches-in-9-hours-what-a-fee-sweep-actually-proves-34b6) — a full cluster from the dataset, and what it cannot tell you

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
pip install solana-launch-forensics
launchforensics --help
```

Python 3.9+. No third-party dependencies — the package installs nothing but itself.

Or run it straight from the repository without installing:

```bash
git clone https://github.com/tdkrHuang/solana-launch-forensics
cd solana-launch-forensics
python3 -m launchforensics --help
```

[PyPI](https://pypi.org/project/solana-launch-forensics/)

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

### `cluster <wallet>` — mints that share evidence

```bash
launchforensics cluster <WALLET> --limit 400
```

Builds a graph whose nodes are wallets and mints and whose edges are individual,
signed facts:

| Edge | Meaning |
|---|---|
| `created` | the wallet paid for the transaction that created the mint |
| `swept` | the wallet collected that mint's creator fee — only the creator can |
| `funded` | SOL moved from one wallet to another |

Connected components containing at least two mints are printed together, with the
signature of every link, so any single claim can be checked on an explorer.

| Flag | Meaning |
|---|---|
| `--min-mints N` | ignore components below N mints (default 2) |
| `--max-mints N` | mints printed per cluster (default 25) |
| `--max-edges N` | evidence lines printed per cluster (default 25) |
| `--out FILE` | write the full JSON result |
| `--json` | print JSON to stdout |

Example output (addresses shortened):

```
wallet      GtTg74ZpUb…4W14
scanned     5 transactions
evidence    created 3, funded 1, swept 3
clusters    1  (minimum 2 mints)

cluster 1: 3 mints, 2 wallets
  links      created 3, funded 1, swept 3
  window     2025-11-16 04:50:00 -> 2025-11-16 05:16:21 (26m 21s)
  wallets
    - GtTg74ZpUb…4W14
    - 8fJ1XKz6Yb…QwZa
  mints
    - EGX8MJT8wd…pump
    - 2ZZhunwtYT…pump
    - 2GoDADTFmh…pump
  evidence
    created  GtTg74ZpUb…4W14 -> EGX8MJT8wd…pump  create1
    funded   8fJ1XKz6Yb…QwZa -> GtTg74ZpUb…4W14  0.05 SOL  fund1
    swept    GtTg74ZpUb…4W14 -> EGX8MJT8wd…pump  sweep1
```

A control wallet — one that created a single token and collected nothing — prints
`No cluster above the threshold.` That silence is the point: the command reports
links it can sign, not wallets it finds interesting.

Shared funding is a link, not proof. Exchanges and faucets fund thousands of
unrelated wallets, so read the `funded` edges with that in mind; `created` and
`swept` are the stronger links because both require control of the wallet.

---

## Dataset

`datasets/clusters.jsonl` collects reproducible cluster records: the seed wallet,
the exact command, the scan bound, the evidence counts and a confidence grade.
The schema is documented in [`datasets/SCHEMA.md`](datasets/SCHEMA.md).

As of 2026-11-21 the committed dataset holds **58 clusters covering
1593 mints**, 41 of them graded `high` (a creator-fee sweep proves
control). It is a sample of pump.fun activity, not a ranking of anyone; see the
schema for how confidence is decided.

```bash
# find seed wallets by sampling recent pump.fun activity
python3 tools/find_seeds.py --sample 150 --merge datasets/seeds.json

# turn seeds into records
python3 tools/build_dataset.py --seeds datasets/seeds.json --limit 200
python3 tools/build_dataset.py --seeds datasets/seeds.json --dry-run

# or loop discovery and scanning unattended until a target is reached
python3 tools/collect_dataset.py --source pools --target 100 --limit 250
```

Fee payers that create a mint, or collect a creator fee, become seeds. A fee
collector is a creator by definition, so sweeps count even when the creation
falls outside the sampled window.

Grading is by the weakest link used to join the mints:

| Grade | Condition |
|---|---|
| `high` | at least one `swept` edge — only a creator can collect the fee |
| `medium` | two or more `created` edges from one wallet |
| `low` | joined only by funding transfers (dropped by default) |

Records are keyed by a hash of their mints, so re-running updates instead of
duplicating, and a rate-limited run keeps what it already wrote.

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

`cluster` writes:

```json
{
  "wallet": "...",
  "scanned_transactions": 400,
  "edge_counts": {"created": 84, "funded": 12, "swept": 61},
  "cluster_count": 2,
  "clusters": [
    {
      "mints": ["...pump", "...pump"],
      "wallets": ["..."],
      "links": {"created": 84, "funded": 12, "swept": 61},
      "first_block_time": 1763268569,
      "last_block_time": 1763272285,
      "edges": [
        {"type": "created", "wallet": "...", "mint": "...pump", "signature": "..."}
      ]
    }
  ]
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
- **Endpoints disagree.** Some public RPCs return an empty signature list for
  addresses they do not index — including wallets that are active. `scan` will
  report `no signatures returned`. Confirm on a second endpoint before treating
  a wallet as inactive, and say which endpoint you used.
- **Not a verdict.** Repeated equal-size payouts and batched creations are patterns,
  not proof of wrongdoing.

---

## Paid reports

Reading the code is free. If you need this applied to a specific wallet — with
the funding chain, payout reconstruction and a PDF you can hand to a community,
a lawyer or an exchange — I write those reports with this tool:

- **Lite $99** — one wallet, 48h
- **Standard $299** — up to 5 wallets, 72h
- **Deep $699** — up to 15 wallets, legal appendix, 5 business days

Every claim carries a signature. Sample report (real case, 96 launches):
[docs/sample-report.md](docs/sample-report.md)

## Tests

```bash
python3 -m pytest -q
```

Fixtures in `tests/fixtures.py` mirror real responses, including a versioned
transaction **without `message.header`** and a Token-2022 `InitializeMint2` nested
inside a pump.fun call. `tests/test_cluster.py` covers the graph rules: a single
mint is never a cluster, shared funding joins two wallets, a sweep joins mints to
the sweeper, and duplicate links collapse without duplicating mints.

---

## License

MIT
