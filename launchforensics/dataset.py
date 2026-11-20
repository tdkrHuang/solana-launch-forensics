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
