"""Turn a list of transaction signatures into evidence edges.

Shared by the ``cluster`` command and the dataset builder so both produce
exactly the same edges from the same input. The function is deliberately
free of printing: callers decide how to report progress.
"""

from __future__ import annotations

from typing import Callable

from . import analytics as A


def collect_edges(
    rpc,
    wallet: str,
    *,
    limit: int = 200,
    on_progress: Callable[[str], None] | None = None,
    on_error: Callable[[str, Exception], None] | None = None,
) -> dict:
    """Scan ``wallet`` and return ``{edges, scanned, failed, stopped_early}``.

    Failures are counted, never raised: one unreachable transaction must not
    discard an otherwise valid scan. The run stops early only when failures
    outnumber successes by a wide margin, which means the RPC is rate
    limiting rather than missing a few blocks.
    """
    say = on_progress or (lambda _msg: None)
    complain = on_error or (lambda _sig, _exc: None)

    sigs = rpc.signatures(wallet, limit=limit)
    edges: list[dict] = []
    scanned = 0
    failed = 0
    stopped_early = False

    for i, sig in enumerate(sigs, 1):
        try:
            tx = rpc.transaction(sig["signature"])
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            failed += 1
            complain(sig["signature"], exc)
            if failed > 20 and failed * 4 > scanned:
                stopped_early = True
                break
            continue
        if not tx:
            continue
        scanned += 1

        info = A.summarize(tx)
        payer = info["fee_payer"]
        where = {
            "signature": sig["signature"],
            "slot": sig["slot"],
            "block_time": sig.get("blockTime"),
        }
        if payer and info["creates"] > 0:
            for mint in info["created_mints"]:
                edges.append({"type": "created", "wallet": payer, "mint": mint, **where})
        if payer:
            for mint in A.swept_mints(tx):
                edges.append({"type": "swept", "wallet": payer, "mint": mint, **where})
        for flow in A.funding_inflows(tx):
            edges.append(
                {
                    "type": "funded",
                    "from": flow["from"],
                    "to": flow["to"],
                    "lamports": flow["lamports"],
                    **where,
                }
            )

        if i % 20 == 0:
            say(f"  {i}/{len(sigs)} transactions")

    # A sweep is only evidence when the same wallet also created the mint in
    # this window. Anyone can submit a fee collection for someone else's mint,
    # so a sweep on its own says nothing about who controls the mint.
    created = {(e["wallet"], e["mint"]) for e in edges if e["type"] == "created"}
    edges = [
        e for e in edges
        if e["type"] != "swept" or (e["wallet"], e["mint"]) in created
    ]

    return {
        "edges": edges,
        "scanned": scanned,
        "failed": failed,
        "stopped_early": stopped_early,
        "requested": len(sigs),
    }
