"""Command line interface for solana-launch-forensics."""

from __future__ import annotations

import argparse
import json
import sys
import time

from . import analytics as A
from .rpc import DEFAULT_RPC, Rpc


def utc(ts: int | None) -> str:
    if not ts:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts))


def short(value: str, keep: int = 8) -> str:
    if not value:
        return "-"
    if len(value) <= keep + 4:
        return value
    return f"{value[:keep]}..{value[-4:]}"


def progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def cmd_scan(args: argparse.Namespace) -> int:
    rpc = Rpc(args.rpc, pause=args.pause, retries=args.retries)
    progress(f"fetching up to {args.limit} signatures for {args.wallet}")

    sigs = rpc.signatures(args.wallet, limit=args.limit)
    if not sigs:
        progress("no signatures returned")
        return 1

    creations: dict[str, dict] = {}
    batches: list[dict] = []
    scanned = 0
    failed = 0

    for i, sig in enumerate(sigs, 1):
        try:
            tx = rpc.transaction(sig["signature"])
        except Exception as exc:  # noqa: BLE001 - a single bad tx must not end the scan
            failed += 1
            progress(f"  ! {short(sig['signature'], 12)}: {exc}")
            if failed > 20 and failed * 4 > scanned:
                progress("too many failures; the RPC is rate limiting. Retry with --rpc <endpoint>")
                break
            continue
        if not tx:
            continue
        scanned += 1
        info = A.summarize(tx)
        if info["creates"] <= 0:
            continue

        entry = {
            "signature": sig["signature"],
            "slot": sig["slot"],
            "block_time": sig.get("blockTime"),
            "creates": info["creates"],
            "mints": info["mints"],
            "err": info["err"],
        }
        if info["creates"] >= 2:
            batches.append(entry)

        for mint in info["mints"]:
            if mint in creations:
                continue
            creations[mint] = {
                "mint": mint,
                "signature": sig["signature"],
                "slot": sig["slot"],
                "block_time": sig.get("blockTime"),
                "batch_size": info["creates"],
            }

        if i % 20 == 0:
            progress(f"  {i}/{len(sigs)} transactions")

    rows = sorted(creations.values(), key=lambda r: r["block_time"] or 0)
    times = [r["block_time"] for r in rows if r["block_time"]]
    window = (max(times) - min(times)) if len(times) > 1 else 0

    result = {
        "wallet": args.wallet,
        "scanned_transactions": scanned,
        "failed_transactions": failed,
        "creations": rows,
        "creation_count": len(rows),
        "window_seconds": window,
        "batch_transactions": batches,
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        progress(f"wrote {args.out}")

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"wallet          {args.wallet}")
    print(f"scanned         {scanned} transactions")
    if failed:
        print(f"failed          {failed} (RPC errors, skipped)")
    print(f"creations       {len(rows)}")
    if window:
        print(f"window          {window // 60}m {window % 60}s")
    if batches:
        print(f"batch txs       {len(batches)}  (multiple mints in one transaction)")

    if rows:
        print()
        print(f"{'created (UTC)':19s}  {'batch':>5s}  {'mint':46s}  tx")
        for r in rows:
            print(
                f"{utc(r['block_time']):19s}  {r['batch_size']:5d}  "
                f"{r['mint']:46s}  {short(r['signature'], 12)}"
            )

    if batches:
        print()
        print("batch transactions:")
        for b in batches:
            print(f"  {b['signature']}")
            print(f"    {b['creates']} creates, {len(b['mints'])} mints, slot {b['slot']}")

    return 0


def cmd_tx(args: argparse.Namespace) -> int:
    rpc = Rpc(args.rpc, pause=args.pause)
    tx = rpc.transaction(args.signature)
    if not tx:
        progress("transaction not found")
        return 1

    info = A.summarize(tx)
    if args.json:
        print(json.dumps(info, indent=2, default=str))
        return 0

    print(f"signature   {args.signature}")
    print(f"slot        {info['slot']}")
    print(f"time        {utc(info['block_time'])} UTC")
    print(f"fee payer   {info['fee_payer']}")
    print(f"signers     {', '.join(info['signers'])}")
    print(f"fee         {A.format_sol(info['fee_lamports'] or 0)} SOL")
    print(f"error       {info['err']}")
    if info["pump_ops"]:
        ops = ", ".join(f"{k} x{v}" if v > 1 else k for k, v in info["pump_ops"].items())
        print(f"pump ops    {ops}")
    print(f"creates     {info['creates']}")
    print(f"mints       {len(info['mints'])} referenced")
    for mint in info["mints"]:
        print(f"  - {mint}")

    transfers = A.system_transfers(tx)
    if transfers:
        print(f"\nSOL transfers ({len(transfers)}):")
        for t in transfers[: args.max_transfers]:
            print(
                f"  {short(t['source'], 10)} -> {short(t['destination'], 10)}  "
                f"{A.format_sol(t['lamports'])} SOL"
            )
        if len(transfers) > args.max_transfers:
            print(f"  ... {len(transfers) - args.max_transfers} more")

    groups = info["equal_size_outflows"]
    if groups:
        print("\nequal-size outflows from signer:")
        for g in groups:
            print(f"  {g['sol']} SOL x {len(g['destinations'])}")
            for d in g["destinations"]:
                print(f"    -> {d}")

    return 0


def cmd_flows(args: argparse.Namespace) -> int:
    rpc = Rpc(args.rpc, pause=args.pause, retries=args.retries)
    progress(f"fetching up to {args.limit} signatures for {args.wallet}")
    sigs = rpc.signatures(args.wallet, limit=args.limit)

    buckets: dict[int, dict] = {}
    scanned = 0
    failed = 0

    for i, sig in enumerate(sigs, 1):
        try:
            tx = rpc.transaction(sig["signature"])
        except Exception as exc:  # noqa: BLE001
            failed += 1
            progress(f"  ! {short(sig['signature'], 12)}: {exc}")
            if failed > 20 and failed * 4 > scanned:
                progress("too many failures; the RPC is rate limiting. Retry with --rpc <endpoint>")
                break
            continue
        if not tx:
            continue
        scanned += 1

        if args.across_tx:
            owner = set(A.signers(tx))
            groups = []
            by_amount: dict[int, list[str]] = {}
            for t in A.system_transfers(tx):
                if t["source"] in owner and t["lamports"] > 0:
                    by_amount.setdefault(t["lamports"], []).append(t["destination"])
            for lamports, dests in by_amount.items():
                groups.append(
                    {
                        "lamports": lamports,
                        "sol": lamports / A.LAMPORTS_PER_SOL,
                        "destinations": dests,
                    }
                )
        else:
            groups = A.equal_size_outflows(tx)

        for group in groups:
            if group["lamports"] < args.min_sol * A.LAMPORTS_PER_SOL:
                continue
            bucket = buckets.setdefault(
                group["lamports"],
                {"lamports": group["lamports"], "sol": group["sol"], "destinations": set(), "txs": []},
            )
            bucket["destinations"].update(group["destinations"])
            bucket["txs"].append(sig["signature"])
        if i % 20 == 0:
            progress(f"  {i}/{len(sigs)} transactions")

    rows = sorted(
        (b for b in buckets.values() if len(b["destinations"]) >= args.min_count),
        key=lambda b: (-len(b["destinations"]), -b["lamports"]),
    )
    result = [
        {
            "sol": r["sol"],
            "lamports": r["lamports"],
            "destination_count": len(r["destinations"]),
            "destinations": sorted(r["destinations"]),
            "transactions": r["txs"],
        }
        for r in rows
    ]

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"wallet": args.wallet, "scanned": scanned, "failed": failed, "groups": result}, fh, indent=2)
        progress(f"wrote {args.out}")

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print(f"wallet      {args.wallet}")
    print(f"scanned     {scanned} transactions")
    if failed:
        print(f"failed      {failed} (RPC errors, skipped)")
    print(f"groups      {len(result)}")
    if not result:
        print("\nNo repeated equal-size outflows above the threshold.")
        return 0

    print()
    for r in result:
        print(f"{r['sol']} SOL x {r['destination_count']} destinations  ({len(r['transactions'])} txs)")
        for d in r["destinations"][:10]:
            print(f"  -> {d}")
        if r["destination_count"] > 10:
            print(f"  ... {r['destination_count'] - 10} more")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="launchforensics",
        description="Read-only forensics for pump.fun style token launches.",
    )
    parser.add_argument("--rpc", default=DEFAULT_RPC, help="Solana RPC endpoint")
    parser.add_argument("--pause", type=float, default=0.35, help="seconds between RPC calls")
    parser.add_argument("--retries", type=int, default=6, help="retries per RPC call")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="list mints created by a wallet")
    scan.add_argument("wallet")
    scan.add_argument("--limit", type=int, default=200, help="transactions to inspect (max 1000)")
    scan.add_argument("--out", help="write full JSON result here")
    scan.add_argument("--json", action="store_true", help="print JSON to stdout")
    scan.set_defaults(func=cmd_scan)

    tx = sub.add_parser("tx", help="inspect a single transaction")
    tx.add_argument("signature")
    tx.add_argument("--max-transfers", type=int, default=25)
    tx.add_argument("--json", action="store_true")
    tx.set_defaults(func=cmd_tx)

    flows = sub.add_parser("flows", help="find repeated equal-size SOL outflows")
    flows.add_argument("wallet")
    flows.add_argument("--limit", type=int, default=100)
    flows.add_argument("--min-sol", type=float, default=0.01, help="ignore transfers below this size")
    flows.add_argument("--min-count", type=int, default=2, help="minimum distinct destinations")
    flows.add_argument(
        "--across-tx",
        action="store_true",
        help="group identical amounts across transactions instead of within one transaction",
    )
    flows.add_argument("--out", help="write full JSON result here")
    flows.add_argument("--json", action="store_true")
    flows.set_defaults(func=cmd_flows)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        progress("interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
