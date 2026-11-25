"""Dataset records: a stable, reproducible description of one cluster.

The point of a published dataset is that someone else can regenerate it and
get the same numbers. So a record stores the seed wallet, the scan bound, the
tool version and the evidence counts -- never a verdict.

Confidence is graded by the weakest link used to join the mints:

``high``
    At least one ``swept`` edge. Only a mint's creator can collect its fee,
    so control is proven rather than inferred.

``medium``
    No sweep, but two or more mints share a creating wallet.

``low``
    Joined only by funding transfers. Exchanges and faucets do this for
    thousands of unrelated wallets, so these are not counted as clusters.
"""

from __future__ import annotations

import hashlib

from . import analytics as A

WINDOW_NOTE = "block_time span of the evidence edges, in seconds"


def cluster_id(cluster: dict) -> str:
    """Deterministic id: the same mints always produce the same id."""
    basis = "|".join(sorted(cluster.get("mints") or []))
    return "c" + hashlib.sha256(basis.encode()).hexdigest()[:12]


def confidence(cluster: dict) -> str:
    links = cluster.get("links") or {}
    if links.get("swept", 0) > 0:
        return "high"
    if links.get("created", 0) >= 2:
        return "medium"
    return "low"


def record(
    cluster: dict,
    *,
    seed_wallet: str,
    scanned: int,
    tool_version: str,
    limit: int,
    source: str = "",
    notes: str = "",
) -> dict:
    """One JSONL line describing a single cluster."""
    first = cluster.get("first_block_time")
    last = cluster.get("last_block_time")
    window = (last - first) if isinstance(first, int) and isinstance(last, int) else 0
    return {
        "cluster_id": cluster_id(cluster),
        "seed_wallet": seed_wallet,
        "wallets": list(cluster.get("wallets") or []),
        "mints": list(cluster.get("mints") or []),
        "mint_count": len(cluster.get("mints") or []),
        "links": dict(cluster.get("links") or {}),
        "confidence": confidence(cluster),
        "first_block_time": first,
        "last_block_time": last,
        "window_seconds": window,
        "scanned_transactions": scanned,
        "scan_limit": limit,
        "tool_version": tool_version,
        "method": f"launchforensics {tool_version} cluster --limit {limit}",
        "source": source,
        "notes": notes,
    }


def seeds_from_transactions(items: list[tuple[str, dict]], *, min_creations: int = 1) -> list[dict]:
    """Wallets that created a mint in a sample of transactions.

    Only creations count. A fee collection cannot identify a creator: the
    pump.fun program lets any signer submit ``CollectCreatorFee``, so the
    payer of a sweep is whoever paid to trigger it, often a bot, not the
    owner of the mint.

    The result is a sample of whoever was active in the window, not a ranking
    of anyone and not an accusation.
    """
    creations: dict[str, int] = {}
    sweeps: dict[str, int] = {}
    for _signature, tx in items:
        info = A.summarize(tx)
        payer = info["fee_payer"]
        if not payer:
            continue
        made = len(info["created_mints"]) if info["creates"] else 0
        if made:
            creations[payer] = creations.get(payer, 0) + made
        collected = A.sweep_count(tx)
        if collected:
            sweeps[payer] = sweeps.get(payer, 0) + collected

    out = []
    for wallet in creations:
        made = creations[wallet]
        if made < min_creations:
            continue
        out.append(
            {
                "wallet": wallet,
                "creations_in_sample": made,
                "sweeps_in_sample": sweeps.get(wallet, 0),
                "evidence": "creation",
            }
        )
    return sorted(out, key=lambda s: (-s["creations_in_sample"], -s["sweeps_in_sample"], s["wallet"]))


def seeds_from_creators(pairs: list[tuple[str, str]]) -> list[dict]:
    """Seeds from ``(mint, creator)`` pairs resolved elsewhere.

    A mint's oldest signature is its creation, and that transaction's fee
    payer is the account that paid to launch it. Counting how many of the
    sampled mints each payer launched is a cheap way to find wallets worth a
    deeper scan, without walking a trade-dominated program log.
    """
    counts: dict[str, int] = {}
    for mint, wallet in pairs:
        if not mint or not wallet:
            continue
        counts[wallet] = counts.get(wallet, 0) + 1

    out = [
        {
            "wallet": wallet,
            "creations_in_sample": count,
            "sweeps_in_sample": 0,
            "evidence": "creation (oldest signature of the mint)",
        }
        for wallet, count in counts.items()
    ]
    return sorted(out, key=lambda s: (-s["creations_in_sample"], s["wallet"]))
