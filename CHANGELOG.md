# Changelog

## 0.3.1 — 2026-11-25

### Fixed

- **Creations are read from the token program's `initializeMint`, not from every
  pump-suffixed account in the transaction.** A pump.fun transaction that
  creates one token usually buys others, and the old code credited the payer
  with all of them. On a 250-transaction scan this changed 76 attributed mints
  to 48 actual creations, which inflated the dataset, the demo sample and two
  articles. Records built before this version must be regenerated.
- **A fee collection is not ownership evidence.** Collection is permissionless:
  any signer can submit `CollectCreatorFee`, and bots do. A `swept` edge is now
  kept only when the same wallet also created that mint in the same scan, and it
  is corroboration, not proof.

### Changed

- Seed discovery uses creations only. A fee payer is not a seed unless it
  created something.
- `summarize()` exposes `created_mints`; `creates_mints` is based on it.

## 0.3.0 — 2026-11-21

### Fixed

- `CollectCreatorFee` (the v1 name) is now counted as a fee sweep. Only the
  three names together — `SweepCreatorFee`, `CollectCreatorFee`,
  `CollectCreatorFeeV2` — cover every collection event pump.fun has emitted.
  Before this, a wallet whose mints were collected with the v1 instruction
  showed no sweep evidence at all, which under-reports ownership rather than
  over-reports it.

### Added

- `launchforensics.dataset` — a record type and stable `cluster_id`
  (`c` + the first 12 hex characters of `sha256` over the sorted mints), so a
  dataset scan is reproducible and a deeper re-scan replaces a shallower one.
- `launchforensics.pipeline.collect_edges` — the edge extraction used by both
  `cluster` and the dataset builder, so a record and a CLI run cannot diverge.
- Browser demo at <https://tdkrhuang.github.io/solana-launch-forensics/demo/>.
  It is a port of the same rules to plain JavaScript and is not part of the
  wheel; `tests/test_demo_parity.py` keeps the two implementations aligned.

### Dataset

- `datasets/clusters.jsonl`: 111 clusters, 2,872 mints, 230 wallets
  (high 78 / medium 33), schema in `datasets/SCHEMA.md`.
