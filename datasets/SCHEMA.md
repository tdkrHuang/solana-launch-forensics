# Cluster dataset

`clusters.jsonl` holds one JSON object per line. Each line describes a set of
mints that the tool joined with evidence, plus the exact command and scan bound
that produced it.

The goal is reproducibility, not volume. A reader should be able to take a
`seed_wallet`, run the `method` line, and recover the same mints.

---

## Fields

| Field | Type | Meaning |
|---|---|---|
| `cluster_id` | string | `c` + first 12 hex chars of `sha256` over the sorted mints joined by `|` |
| `seed_wallet` | string | wallet passed to `cluster` |
| `wallets` | array | every wallet that appears in the cluster's evidence |
| `mints` | array | mints in the connected component |
| `mint_count` | int | `len(mints)`, for sorting |
| `links` | object | edge counts by type: `created`, `swept`, `funded` |
| `confidence` | enum | `high`, `medium`, `low` — see below |
| `first_block_time` | int \| null | earliest `blockTime` among the edges |
| `last_block_time` | int \| null | latest `blockTime` among the edges |
| `window_seconds` | int | `last_block_time - first_block_time`, or 0 |
| `scanned_transactions` | int | transactions actually decoded for this seed |
| `scan_limit` | int | `--limit` used |
| `tool_version` | string | package version |
| `method` | string | the exact command |
| `source` | string | where the seed came from |
| `notes` | string | provenance note. `seed sample: …` counts the discovery sample, not the cluster scan — compare `links` for what the scan found |

---

## Confidence grading

| Grade | Condition | Why |
|---|---|---|
| `high` | at least one mint with both `created` and `swept` by the same wallet | the wallet launched the mint and submitted its fee collection; both signatures are in the record |
| `medium` | no sweep, `links.created >= 2` | one wallet paid to create both mints; strong but not exclusive |
| `low` | joined only by `funded` edges | exchanges and faucets fund unrelated wallets; not counted as a cluster |

> **2026-11-25:** records committed before this date were built with the old
> attribution, which counted every pump mint touched by a create transaction.
> Rebuild before quoting any count from them. `swept` now requires a matching
> `created` edge from the same wallet, because fee collection is permissionless.

`tools/build_dataset.py` drops `low` by default (`--min-confidence medium`).

The dataset never contains a judgement about intent. "These mints share a
creator" is a fact; "this is fraud" is not in the data.

---

## Regenerating

```bash
python3 tools/build_dataset.py --seeds datasets/seeds.json --limit 200
```

- Append-only: records are keyed by `cluster_id`, so re-running updates instead
  of duplicating.
- Resumable: a rate-limited run stops and keeps what it already wrote.
- Offline check: `--dry-run` validates the seed list without network access.
- One scan per seed: a deeper re-scan replaces that seed's earlier records, so
  the same wallet cannot appear twice with different mint sets.

---

## Finding seeds

```bash
python3 tools/find_seeds.py --sample 150 --merge datasets/seeds.json
```

Samples the newest transactions that touch pump.fun and keeps the fee payers
that created a mint **or collected a creator fee**. A fee collector is by
definition a creator, so sweeps count even when the creation falls outside the
sampled window. The output is a sample of the window, not a ranking.

---

## Cost and endpoint

`clusters.jsonl` is generated, not committed as a fixture: each scan needs live
RPC. Measured on the public endpoint from one machine:

| Endpoint | Throughput | Note |
|---|---|---|
| `api.mainnet-beta.solana.com` | ~1 s/tx when healthy, ~11 s/tx under load | starts timing out after sustained use |
| any dedicated free-tier node | much faster | needs an API key, no KYC |

A 200-transaction scan is therefore minutes, not seconds, and a 300-seed run is
hours. The builder is resumable precisely because of this: run it in batches,
stop when the endpoint starts refusing, run again later.

```bash
# batch 1
python3 tools/build_dataset.py --seeds datasets/seeds.json --limit 100
# later, same command; existing records are updated in place
```

Point `--rpc` (or `SOLANA_RPC_URL`) at a dedicated endpoint for a full run.

---

## Adding a seed

Add an object to `seeds.json`:

```json
{
  "wallet": "<base58>",
  "source": "how this wallet was found",
  "notes": "what is notable about it"
}
```

Use public chain data only. Do not add wallets in order to identify a private
individual; the purpose is to test the method.

---

## What the committed dataset contains

Snapshot, 2026-11-26 (rebuilt after the attribution fix):

| Measure | Value |
|---|---|
| clusters | 27 |
| mints covered | 1,224 |
| wallets | 27 |
| graded `high` | 24 |
| graded `medium` | 3 |
| median cluster size | 40 mints |
| largest cluster | 146 mints |
| evidence edges | 1,224 `created`, 327 `swept`, 149 `funded` |

Of 27 clusters, 26 hold ten or more mints and 6 hold fifty or more. The
distribution is heavy-tailed: most wallets launch once, a small number launch
continuously, and the dataset is aimed at the second group.

Thirty seeds were rescanned at 250 transactions each; three produced no cluster
of two or more mints and are absent. The previous snapshot (111 clusters, 2,872
mints) was built with the old attribution and is kept only in git history.

### What it does not say

- It does not say a cluster is fraudulent. It says mints share a paid creator,
  or that one wallet collects their fees.
- It is not exhaustive. Seeds come from a public pool feed over a few hours, so
  the dataset is a sample of that window.
- It does not identify people. Only public keys.
