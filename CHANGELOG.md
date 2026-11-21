# Changelog

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
