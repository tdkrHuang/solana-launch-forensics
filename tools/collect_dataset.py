#!/usr/bin/env python3
"""Collect cluster records until a target is reached, or the night ends.

Two steps repeat: sample pump.fun activity for new seed wallets, then scan each
seed and store the clusters it produces. Both steps are resumable, so stopping
mid-run loses nothing.

    python3 tools/collect_dataset.py --rpc "$HELIUS_URL" --target 100
    python3 tools/collect_dataset.py --dry-run --target 100

Stop conditions, whichever comes first: the target record count, the round
limit, or the time budget. Foundation grants are not paid by the hour; the
point is to leave a reproducible dataset behind, not to burn credits.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def count_records(path: pathlib.Path, min_confidence: str) -> int:
    if not path.exists():
        return 0
    rank = {"low": 0, "medium": 1, "high": 2}
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rank.get(rec.get("confidence", "low"), 0) >= rank[min_confidence]:
            total += 1
    return total


SECRET = re.compile(r"(api-key=)[^&\s]+")


def redact(text: str) -> str:
    """Never print an API key, even inside a logged command line."""
    return SECRET.sub(r"\1***", text)


def run(cmd: list[str], env: dict[str, str] | None = None) -> int:
    # Endpoints travel through the environment, not argv, so the key stays out
    # of `ps` output on a shared machine.
    print("\n$ " + redact(" ".join(cmd)), flush=True)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repeatedly discover seeds and build records.")
    parser.add_argument("--seeds", default="datasets/seeds.json")
    parser.add_argument("--out", default="datasets/clusters.jsonl")
    parser.add_argument("--target", type=int, default=100, help="records to reach")
    parser.add_argument("--rounds", type=int, default=6, help="discovery rounds at most")
    parser.add_argument("--sample", type=int, default=150, help="program txs per discovery page")
    parser.add_argument("--pages", type=int, default=1, help="history pages per discovery round")
    parser.add_argument("--source", choices=["program", "pools"], default="program")
    parser.add_argument("--pools-pages", type=int, default=10, help="20 fresh pools per page")
    parser.add_argument("--limit", type=int, default=60, help="transactions scanned per seed")
    parser.add_argument("--min-confidence", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--sleep", type=int, default=20, help="seconds between rounds")
    parser.add_argument("--budget-minutes", type=int, default=0, help="0 means no time limit")
    parser.add_argument("--rpc", default=None)
    parser.add_argument("--pause", type=float, default=0.25)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    out_path = pathlib.Path(args.out)
    seeds_path = pathlib.Path(args.seeds)
    start = time.time()
    deadline = start + args.budget_minutes * 60 if args.budget_minutes else None

    print(f"target   {args.target} records (min confidence {args.min_confidence})")
    print(f"seeds    {seeds_path}")
    print(f"output   {out_path}")
    print(f"current  {count_records(out_path, args.min_confidence)} records")

    if args.dry_run:
        for r in range(1, args.rounds + 1):
            print(
                f"  round {r}: discover {args.source} "
                f"(--sample {args.sample} x {args.pages}, --pools-pages {args.pools_pages}), "
                f"build --limit {args.limit}"
            )
        return 0

    child_env = os.environ.copy()
    child_env["PYTHONUNBUFFERED"] = "1"
    if args.rpc:
        child_env["SOLANA_RPC_URL"] = args.rpc
    print("endpoint " + redact(child_env.get("SOLANA_RPC_URL", "(default)")))

    common = [
        "--pause", str(args.pause),
        "--retries", str(args.retries),
        "--timeout", str(args.timeout),
    ]

    for round_no in range(1, args.rounds + 1):
        have = count_records(out_path, args.min_confidence)
        print(f"\n=== round {round_no}: {have}/{args.target} records ===")
        if have >= args.target:
            break
        if deadline and time.time() > deadline:
            print("time budget reached")
            break

        run(
            [sys.executable, "tools/find_seeds.py", "--source", args.source,
             "--sample", str(args.sample), "--pages", str(args.pages),
             "--pools-pages", str(args.pools_pages), "--merge", str(seeds_path)]
            + common,
            env=child_env,
        )
        run(
            [sys.executable, "tools/build_dataset.py", "--seeds", str(seeds_path),
             "--out", str(args.out), "--limit", str(args.limit),
             "--min-confidence", args.min_confidence]
            + common,
            env=child_env,
        )

        after = count_records(out_path, args.min_confidence)
        print(f"round {round_no} finished: {after}/{args.target} records")
        if after == have:
            print("  no progress this round; increasing the sample next time")
            args.sample = int(args.sample * 1.5)
        if round_no < args.rounds and args.sleep:
            time.sleep(args.sleep)

    total = count_records(out_path, args.min_confidence)
    elapsed = int(time.time() - start)
    print(f"\nrecords  {total}/{args.target} in {elapsed // 60}m {elapsed % 60}s")
    if total < args.target:
        print("Re-run with a bigger --rounds or --sample to continue. Nothing is lost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
