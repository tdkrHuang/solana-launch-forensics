"""Group mints into clusters from evidence edges.

A cluster is a connected component in a graph whose nodes are wallets and
mints, and whose edges are individual, signed facts:

``created``
    ``wallet -> mint``. The wallet paid for the transaction that created it.

``swept``
    ``wallet -> mint``. The wallet submitted a collection of that mint's creator
    fee, and the same wallet also created the mint in the same scan. Collection
    is permissionless, so on its own it is a payment, not ownership evidence;
    it is kept as corroboration of a creation that is already in the graph.

``funded``
    ``wallet -> wallet``. SOL moved from one wallet to the other. Shared
    funding is a link, not proof: exchanges and faucets fund thousands of
    unrelated wallets.

Every edge keeps its signature, so a reader can check any single link on an
explorer without trusting the tool.
"""

from __future__ import annotations

from collections import Counter


class _UnionFind:
    """Path-halving union-find over string node ids."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def find(self, node: str) -> str:
        self._parent.setdefault(node, node)
        root = node
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[node] != root:
            self._parent[node], node = root, self._parent[node]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank.get(ra, 0) < self._rank.get(rb, 0):
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._rank[ra] = self._rank.get(ra, 0) + 1


def _endpoints(edge: dict) -> list[tuple[str, str]]:
    """Typed nodes touched by one edge."""
    kind = edge.get("type")
    if kind in {"created", "swept"}:
        wallet, mint = edge.get("wallet"), edge.get("mint")
        return [("w", wallet), ("m", mint)] if wallet and mint else []
    if kind == "funded":
        src, dst = edge.get("from"), edge.get("to")
        return [("w", src), ("w", dst)] if src and dst else []
    return []


def _edge_key(edge: dict) -> tuple:
    """Identity used to drop duplicate edges from overlapping scans.

    A mint is created once, and a wallet's control of a mint is one fact no
    matter how many times its fee is swept, so those links collapse by
    participant. Funding transfers stay separate: two payments of the same
    size are two pieces of evidence.
    """
    nodes = tuple(sorted(f"{p}:{v}" for p, v in _endpoints(edge)))
    if edge.get("type") in {"created", "swept"}:
        return (edge.get("type"), nodes)
    return (edge.get("type"), nodes, edge.get("signature"))


def _order(edge: dict) -> int:
    t = edge.get("block_time")
    return t if isinstance(t, int) else -1


def dedupe_edges(edges: list[dict]) -> list[dict]:
    """Drop repeated links, keeping the earliest signature for each."""
    kept: dict[tuple, dict] = {}
    for edge in edges:
        if not _endpoints(edge):
            continue
        key = _edge_key(edge)
        previous = kept.get(key)
        if previous is None:
            kept[key] = edge
            continue
        if _order(edge) >= 0 and (
            _order(previous) < 0 or _order(edge) < _order(previous)
        ):
            kept[key] = edge
    return list(kept.values())


def build_clusters(edges: list[dict], *, min_mints: int = 2) -> list[dict]:
    """Return connected components that contain at least ``min_mints`` mints.

    Components with a single mint are dropped by default: one creation says
    nothing about a cluster, and printing it would make a control wallet look
    suspicious.
    """
    uf = _UnionFind()
    kept = dedupe_edges(edges)

    for edge in kept:
        endpoints = _endpoints(edge)
        first = f"{endpoints[0][0]}:{endpoints[0][1]}"
        for prefix, value in endpoints[1:]:
            uf.union(first, f"{prefix}:{value}")
        uf.find(first)

    components: dict[str, dict] = {}
    for edge in kept:
        endpoints = _endpoints(edge)
        root = uf.find(f"{endpoints[0][0]}:{endpoints[0][1]}")
        comp = components.setdefault(
            root,
            {"mints": {}, "wallets": {}, "edges": [], "times": []},
        )
        comp["edges"].append(edge)
        for prefix, value in endpoints:
            if prefix == "m":
                comp["mints"][value] = None
            else:
                comp["wallets"][value] = None
        if isinstance(edge.get("block_time"), int):
            comp["times"].append(edge["block_time"])

    out: list[dict] = []
    for comp in components.values():
        mints = list(comp["mints"])
        if len(mints) < min_mints:
            continue
        times = comp["times"]
        out.append(
            {
                "mints": mints,
                "wallets": list(comp["wallets"]),
                "links": dict(Counter(e["type"] for e in comp["edges"])),
                "first_block_time": min(times) if times else None,
                "last_block_time": max(times) if times else None,
                "edges": sorted(
                    comp["edges"],
                    key=lambda e: (e.get("block_time") or 0, e.get("signature") or ""),
                ),
            }
        )

    return sorted(out, key=lambda c: (-len(c["mints"]), -len(c["wallets"])))
