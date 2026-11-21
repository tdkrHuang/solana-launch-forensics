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
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from launchforensics import analytics as A  # noqa: E402
from launchforensics.dataset import seeds_from_creators, seeds_from_transactions  # noqa: E402
from launchforensics.rpc import Rpc  # noqa: E402

PUMP_PROGRAM = A.PUMP_PROGRAM
POOLS_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"


def _get_json(url: str, *, attempts: int = 5) -> dict:
    """GET with backoff. Public feeds rate limit, and a 429 is not a failure."""
    delay = 8.0
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(
            url,
            headers={"user-agent": "solana-launch-forensics", "accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == attempts:
                raise
            print(f"  rate limited, waiting {delay:.0f}s", file=sys.stderr)
            time.sleep(delay)
            delay *= 2
    return {}


def new_pool_mints(pages: int, *, pump_only: bool = True) -> list[str]:
    """Mints of newly created Solana pools, newest first.

    A launch program's own log is dominated by trades -- thousands of swaps per
    creation -- so sampling it is a poor way to find creators. The pool feed is
    the opposite: one call returns twenty fresh tokens. No key is required.
    """
    mints: dict[str, None] = {}
    for page in range(1, pages + 1):
        payload = _get_json(f"{POOLS_URL}?page={page}")
        rows = payload.get("data") or []
        if not rows:
            break
        for row in rows:
            dex = ((row.get("relationships") or {}).get("dex") or {}).get("data", {}).get("id", "")
            if pump_only and not dex.startswith("pump"):
                continue
            token = ((row.get("relationships") or {}).get("base_token") or {}).get("data", {}).get("id", "")
            mint = token.split("_", 1)[-1]
            if mint:
                mints[mint] = None
        print(f"  pool page {page}: {len(rows)} pools, {len(mints)} pump mints", file=sys.stderr)
        time.sleep(2.5)  # the public pool feed allows ~30 calls a minute
    return list(mints)


def creators_for_mints(rpc: Rpc, mints: list[str]) -> list[tuple[str, str]]:
    """``(mint, creator)`` by reading each mint's oldest signature."""
    pairs: list[tuple[str, str]] = []
    for i, mint in enumerate(mints, 1):
        try:
            sigs = rpc.signatures(mint, limit=1000)
            if not sigs:
                continue
            tx = rpc.transaction(sigs[-1]["signature"])
        except Exception as exc:  # noqa: BLE001 - one mint must not stop the scan
            print(f"  ! {mint[:8]}: {exc}", file=sys.stderr)
            continue
        payer = A.fee_payer(tx) if tx else None
        if payer:
            pairs.append((mint, payer))
        if i % 25 == 0:
            print(f"  resolved {i}/{len(mints)} mints", file=sys.stderr)
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sample recent launches to find seed wallets.")
    parser.add_argument("--source", choices=["program", "pools"], default="program")
    parser.add_argument("--sample", type=int, default=100, help="program transactions per page")
    parser.add_argument("--pages", type=int, default=1, help="pages of history to walk back")
    parser.add_argument("--pools-pages", type=int, default=10, help="20 fresh pools per page")
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

    if args.source == "pools":
        mints = new_pool_mints(args.pools_pages)
        print(f"{len(mints)} fresh pump mints from {args.pools_pages} pool pages", file=sys.stderr)
        pairs = creators_for_mints(rpc, mints)
        found = seeds_from_creators(pairs)
        source = (
            f"new pump.fun pools (GeckoTerminal), {len(mints)} mints sampled, "
            f"{len(found)} creators"
        )
        return _merge_and_report(found, source, args, failed=len(mints) - len(pairs))

    print(
        f"sampling {args.sample} signatures x {args.pages} page(s) of {PUMP_PROGRAM[:8]}...",
        file=sys.stderr,
    )

    items: list[tuple[str, dict]] = []
    failed = 0
    cursor = None
    for page in range(1, args.pages + 1):
        sigs = rpc.signatures(PUMP_PROGRAM, limit=args.sample, before=cursor)
        if not sigs:
            break
        print(f"  page {page}: {len(sigs)} signatures", file=sys.stderr)
        for i, sig in enumerate(sigs, 1):
            try:
                tx = rpc.transaction(sig["signature"])
            except Exception as exc:  # noqa: BLE001 - skip and count
                failed += 1
                print(f"  ! {sig['signature'][:12]}: {exc}", file=sys.stderr)
                continue
            if tx:
                items.append((sig["signature"], tx))
            if i % 50 == 0:
                print(f"    {i}/{len(sigs)} decoded ({failed} failed)", file=sys.stderr)
        cursor = sigs[-1]["signature"]
        if len(sigs) < args.sample:
            break

    found = seeds_from_transactions(items, min_creations=args.min_creations)
    source = (
        f"random sample of pump.fun activity, n={len(items)} txs "
        f"over {args.pages} page(s), {len(found)} creators"
    )

    return _merge_and_report(found, source, args, failed=failed)


def _merge_and_report(found: list[dict], source: str, args, *, failed: int = 0) -> int:
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
        # This counts the seed-discovery sample, not the cluster scan. Without
        # the prefix a record reads as if its cluster had one creation while
        # its `links` object says 108, which looks like a contradiction.
        notes = (
            f"seed sample: {entry['creations_in_sample']} creations, "
            f"{entry['sweeps_in_sample']} fee collections"
        )
        if current is None:
            seeds.append({"wallet": entry["wallet"], "source": source, "notes": notes})
            added += 1
        elif args.overwrite_source:
            current.setdefault("notes", notes)
            current["source"] = source

    if args.sort_key == "creations":
        def key(s):
            return (-s.get("creations_in_sample", 0), -s.get("sweeps_in_sample", 0), s["wallet"])
    else:
        def key(s):
            return s["wallet"]
    seeds.sort(key=key)

    print(
        f"\n{len(found)} creators in the sample, {added} new seeds, "
        f"{len(seeds)} total ({failed} skipped)",
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
