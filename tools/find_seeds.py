#!/usr/bin/env python3
"""Find seed wallets by sampling recent activity of a launch program.

Instead of guessing addresses, this reads the newest transactions that touch
pump.fun and keeps the accounts that paid to create a mint. The output is a
sample of whoever was launching in that window -- stated as a sample, never as
a ranking or an accusation.

    python3 tools/find_seeds.py --sample 120 --min-creations 1
    python3 tools/find_seeds.py --sample 60 --merge datasets/seeds.json

Seeds are merged into the seed file, existing entries keep their `source`
unless `--overwrite-source` is passed.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launchforensics import analytics as A  # noqa: E402
from launchforensics.dataset import seeds_from_transactions  # noqa: E402
from launchforensics.rpc import Rpc  # noqa: E402

PUMP_PROGRAM = A.PUMP_PROGRAM


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample recent launches to find seed wallets.")
    parser.add_argument("--sample", type=int, default=100, help="program transactions to inspect")
    parser.add_argument("--min-creations", type=int, default=1)
    parser.add_argument("--merge", help="seed file to merge into")
    parser.add_argument("--overwrite-source", action="store_true")
    parser.add_argument("--sort-key", choices=["wallet", "creations"], default="creations")
    parser.add_argument("--rpc", default=None)
    parser.add_argument("--pause", type=float, default=0.3)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--json", action="store_true", help="print the seed list")
    args = parser.parse_args(argv)

    kwargs = {"pause": args.pause, "retries": args.retries, "timeout": args.timeout}
    rpc = Rpc(args.rpc, **kwargs) if args.rpc else Rpc(**kwargs)

    print(f"sampling {args.sample} signatures of {PUMP_PROGRAM[:8]}...", file=sys.stderr)
    sigs = rpc.signatures(PUMP_PROGRAM, limit=args.sample)
    print(f"  got {len(sigs)} signatures", file=sys.stderr)

    items: list[tuple[str, dict]] = []
    failed = 0
    for i, sig in enumerate(sigs, 1):
        try:
            tx = rpc.transaction(sig["signature"])
        except Exception as exc:  # noqa: BLE001 - skip and count
            failed += 1
            print(f"  ! {sig['signature'][:12]}: {exc}", file=sys.stderr)
            continue
        if tx:
            items.append((sig["signature"], tx))
        if i % 20 == 0:
            print(f"  {i}/{len(sigs)} decoded ({failed} failed)", file=sys.stderr)

    found = seeds_from_transactions(items, min_creations=args.min_creations)
    source = f"random sample of pump.fun activity, n={len(items)} txs, {len(found)} creators"

    seeds = []
    if args.merge:
        path = pathlib.Path(args.merge)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            seeds = existing if isinstance(existing, list) else existing.get("seeds", [])
    known = {s["wallet"]: s for s in seeds}
    added = 0
    for entry in found:
        current = known.get(entry["wallet"])
        if current is None:
            seeds.append(
                {
                    "wallet": entry["wallet"],
                    "source": source,
                    "notes": f"{entry['creations_in_sample']} creations, {entry['sweeps_in_sample']} fee collections in the sample",
                }
            )
            added += 1
        elif args.overwrite_source:
            current.setdefault(
                "notes",
                f"{entry['creations_in_sample']} creations, "
                f"{entry['sweeps_in_sample']} fee collections in the sample",
            )
            current["source"] = source

    if args.sort_key == "creations":
        key = lambda s: (-s.get("creations_in_sample", 0), -s.get("sweeps_in_sample", 0), s["wallet"])
    else:
        key = lambda s: s["wallet"]
    seeds.sort(key=key)

    print(
        f"\n{len(found)} creators in the sample, {added} new seeds, "
        f"{len(seeds)} total ({failed} txs failed)",
        file=sys.stderr,
    )

    if args.merge:
        pathlib.Path(args.merge).write_text(json.dumps(seeds, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.merge}", file=sys.stderr)
    if args.json or not args.merge:
        print(json.dumps(found, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
