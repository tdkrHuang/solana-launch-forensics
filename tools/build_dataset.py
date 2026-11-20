#!/usr/bin/env python3
"""Build datasets/clusters.jsonl from a list of seed wallets.

The output is append-only and resumable: every cluster carries a
deterministic id, so re-running with the same seeds updates records in place
instead of duplicating them.

    python3 tools/build_dataset.py --seeds datasets/seeds.json
    python3 tools/build_dataset.py --seeds datasets/seeds.json --limit 100 --min-confidence medium
    python3 tools/build_dataset.py --seeds datasets/seeds.json --dry-run

Runs offline with ``--dry-run``: it validates the seed file and prints what
would be scanned without touching the network.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launchforensics import __version__  # noqa: E402
from launchforensics.cluster import build_clusters  # noqa: E402
from launchforensics.dataset import record  # noqa: E402
from launchforensics.pipeline import collect_edges  # noqa: E402
from launchforensics.rpc import Rpc  # noqa: E402

RANK = {"low": 0, "medium": 1, "high": 2}


def load_seeds(path: pathlib.Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("seeds", [])
    seeds = []
    for entry in data:
        if isinstance(entry, str):
            entry = {"wallet": entry}
        if not entry.get("wallet"):
            raise SystemExit(f"seed without a wallet: {entry!r}")
        seeds.append(entry)
    return seeds


def load_existing(path: pathlib.Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        out[rec["cluster_id"]] = rec
    return out


def load_scanned(path: pathlib.Path) -> dict[str, int]:
    """How deep each seed has already been scanned.

    Without this, an unattended loop would re-scan every known seed on every
    round and spend its whole budget on the first few wallets.
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_scanned(path: pathlib.Path, state: dict[str, int]) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a cluster dataset from seed wallets.")
    parser.add_argument("--seeds", default="datasets/seeds.json")
    parser.add_argument("--out", default="datasets/clusters.jsonl")
    parser.add_argument("--limit", type=int, default=200, help="transactions per seed")
    parser.add_argument("--min-mints", type=int, default=2)
    parser.add_argument(
        "--min-confidence",
        choices=["low", "medium", "high"],
        default="medium",
        help="drop records below this grade (default: medium)",
    )
    parser.add_argument("--rpc", default=None)
    parser.add_argument("--pause", type=float, default=0.35)
    parser.add_argument("--retries", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--state", help="scan-depth bookkeeping (default: <out>.scanned.json)")
    parser.add_argument("--force", action="store_true", help="re-scan seeds already covered")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    seeds_path = pathlib.Path(args.seeds)
    out_path = pathlib.Path(args.out)
    seeds = load_seeds(seeds_path)

    print(f"seeds   {len(seeds)} from {seeds_path}")
    if args.dry_run:
        for seed in seeds[:20]:
            print(f"  would scan {seed['wallet']}  {seed.get('source', '')}")
        if len(seeds) > 20:
            print(f"  ... {len(seeds) - 20} more")
        print(f"would write to {out_path} (limit {args.limit}, min {args.min_confidence})")
        return 0

    rpc_kwargs = {"pause": args.pause, "retries": args.retries, "timeout": args.timeout}
    rpc = Rpc(args.rpc, **rpc_kwargs) if args.rpc else Rpc(**rpc_kwargs)
    records = load_existing(out_path)
    state_path = pathlib.Path(args.state) if args.state else out_path.with_suffix(".scanned.json")
    scanned_state = load_scanned(state_path)
    added = 0
    skipped = 0
    started = time.time()

    for n, seed in enumerate(seeds, 1):
        wallet = seed["wallet"]
        done = scanned_state.get(wallet, -1)
        if not args.force and done >= args.limit:
            print(f"[{n}/{len(seeds)}] {wallet} — already scanned to {done}, skipping")
            continue
        print(f"[{n}/{len(seeds)}] {wallet}")
        scan = collect_edges(
            rpc,
            wallet,
            limit=args.limit,
            on_progress=lambda msg: None,
            on_error=lambda sig, exc: print(f"  ! {sig[:12]}: {exc}"),
        )
        if scan["stopped_early"]:
            print("  ! RPC appears to be rate limiting; stopping")
            break

        scanned_state[wallet] = max(done, scan["scanned"])
        save_scanned(state_path, scanned_state)

        clusters = build_clusters(scan["edges"], min_mints=args.min_mints)
        print(f"  scanned {scan['scanned']} txs, {len(clusters)} clusters")

        fresh = []
        for cluster in clusters:
            rec = record(
                cluster,
                seed_wallet=wallet,
                scanned=scan["scanned"],
                tool_version=__version__,
                limit=args.limit,
                source=seed.get("source", ""),
                notes=seed.get("notes", ""),
            )
            if RANK[rec["confidence"]] < RANK[args.min_confidence]:
                skipped += 1
                continue
            fresh.append(rec)

        # One scan per seed: a deeper scan replaces what a shallower one found,
        # so the same wallet cannot appear twice with different mint sets.
        previous = [r for r in records.values() if r["seed_wallet"] == wallet]
        best = max((r["scanned_transactions"] for r in previous), default=-1)
        if fresh and scan["scanned"] >= best:
            for r in previous:
                records.pop(r["cluster_id"], None)
            for rec in fresh:
                if rec["cluster_id"] not in records:
                    added += 1
                records[rec["cluster_id"]] = rec
        elif fresh:
            print(f"  kept the earlier scan ({best} txs); this one saw {scan['scanned']}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in sorted(records.values(), key=lambda r: (-r["mint_count"], r["cluster_id"])):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    elapsed = int(time.time() - started)
    by_grade: dict[str, int] = {}
    for rec in records.values():
        by_grade[rec["confidence"]] = by_grade.get(rec["confidence"], 0) + 1
    print(f"\nwrote    {len(records)} records to {out_path}  ({added} new, {skipped} below threshold)")
    print("grades   " + ", ".join(f"{k} {v}" for k, v in sorted(by_grade.items())))
    print(f"elapsed  {elapsed // 60}m {elapsed % 60}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
