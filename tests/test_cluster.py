import argparse
import contextlib
import copy
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fixtures
from launchforensics import analytics as A
from launchforensics import cli
from launchforensics.cluster import build_clusters

FUNDER = "8fJ1XKz6Yb3kQp2mNv7rLd5sTfA9uE2xC7hRmLnQwZa"


def funded_create_tx(mint: str = fixtures.MINT_B, lamports: int = 50_000_000) -> dict:
    """A creation transaction whose fee payer was funded in the same tx."""
    tx = copy.deepcopy(fixtures.single_create_tx(mint))
    message = tx["transaction"]["message"]
    message["accountKeys"].append(
        {"pubkey": FUNDER, "signer": False, "writable": True, "source": "transaction"}
    )
    message["instructions"].append(
        {
            "programId": fixtures.SYSTEM_PROGRAM,
            "parsed": {
                "type": "transfer",
                "info": {"source": FUNDER, "destination": fixtures.SIGNER, "lamports": lamports},
            },
            "program": "system",
            "stackHeight": None,
        }
    )
    return tx


def created(wallet: str, mint: str, signature: str = "sig", block_time: int = 1000) -> dict:
    return {
        "type": "created",
        "wallet": wallet,
        "mint": mint,
        "signature": signature,
        "block_time": block_time,
    }


def swept(wallet: str, mint: str, signature: str = "sweep", block_time: int = 1000) -> dict:
    return {
        "type": "swept",
        "wallet": wallet,
        "mint": mint,
        "signature": signature,
        "block_time": block_time,
    }


def funded(src: str, dst: str, signature: str = "fund", lamports: int = 50_000_000) -> dict:
    return {
        "type": "funded",
        "from": src,
        "to": dst,
        "lamports": lamports,
        "signature": signature,
        "block_time": 1000,
    }


# -- analytics: sweeps -----------------------------------------------------
def test_sweep_count_reads_the_instruction_name():
    assert A.sweep_count(fixtures.sweep_tx(7)) == 7


def test_sweep_is_never_counted_as_a_creation():
    assert A.create_count(fixtures.sweep_tx(7)) == 0


def test_swept_mints_returns_the_referenced_mints():
    assert A.swept_mints(fixtures.sweep_tx(3)) == [
        fixtures.MINT_A,
        fixtures.MINT_B,
        fixtures.MINT_C,
    ]


def test_swept_mints_is_empty_for_a_creation():
    assert A.swept_mints(fixtures.create_tx_v0()) == []


# -- analytics: funding ----------------------------------------------------
def test_funding_inflows_into_the_fee_payer():
    flows = A.funding_inflows(funded_create_tx())
    assert len(flows) == 1
    assert flows[0]["from"] == FUNDER
    assert flows[0]["to"] == fixtures.SIGNER
    assert flows[0]["lamports"] == 50_000_000


def test_funding_inflows_ignores_outgoing_transfers():
    tx = copy.deepcopy(fixtures.batch_create_tx(2))
    assert A.funding_inflows(tx) == []


# -- clustering ------------------------------------------------------------
def test_one_mint_is_not_a_cluster():
    assert build_clusters([created(fixtures.SIGNER, fixtures.MINT_A)]) == []


def test_two_mints_from_one_wallet_cluster_together():
    clusters = build_clusters(
        [
            created(fixtures.SIGNER, fixtures.MINT_A, "sig-a"),
            created(fixtures.SIGNER, fixtures.MINT_B, "sig-b"),
        ]
    )
    assert len(clusters) == 1
    assert clusters[0]["wallets"] == [fixtures.SIGNER]
    assert set(clusters[0]["mints"]) == {fixtures.MINT_A, fixtures.MINT_B}


def test_shared_funder_links_two_wallets():
    clusters = build_clusters(
        [
            created(fixtures.SIGNER, fixtures.MINT_A, "sig-a"),
            funded(FUNDER, fixtures.SIGNER, "fund-a"),
            created(fixtures.SPLIT_A, fixtures.MINT_B, "sig-b"),
            funded(FUNDER, fixtures.SPLIT_A, "fund-b"),
        ]
    )
    assert len(clusters) == 1
    assert set(clusters[0]["wallets"]) == {fixtures.SIGNER, fixtures.SPLIT_A, FUNDER}
    assert clusters[0]["links"]["funded"] == 2


def test_sweep_evidence_joins_a_mint_to_the_sweeper():
    clusters = build_clusters(
        [
            created(fixtures.SIGNER, fixtures.MINT_A, "sig-a"),
            funded(fixtures.SIGNER, fixtures.SPLIT_B, "sig-f"),
            swept(fixtures.SPLIT_B, fixtures.MINT_B, "sig-b"),
            swept(fixtures.SPLIT_B, fixtures.MINT_C, "sig-c"),
        ]
    )
    assert len(clusters) == 1
    assert set(clusters[0]["mints"]) == {fixtures.MINT_A, fixtures.MINT_B, fixtures.MINT_C}
    assert clusters[0]["links"]["swept"] == 2
    assert clusters[0]["links"]["funded"] == 1


def test_duplicate_edges_do_not_duplicate_mints():
    edge = created(fixtures.SIGNER, fixtures.MINT_A, "sig-a")
    clusters = build_clusters([edge, dict(edge)])
    assert clusters == []

    with_two = build_clusters([edge, dict(edge), created(fixtures.SIGNER, fixtures.MINT_B, "sig-b")])
    assert len(with_two[0]["mints"]) == 2


def test_edges_keep_their_signature():
    clusters = build_clusters(
        [
            created(fixtures.SIGNER, fixtures.MINT_A, "sig-a"),
            created(fixtures.SIGNER, fixtures.MINT_B, "sig-b"),
        ]
    )
    assert {e["signature"] for e in clusters[0]["edges"]} == {"sig-a", "sig-b"}


def test_clusters_are_sorted_by_mint_count():
    clusters = build_clusters(
        [
            created(fixtures.SIGNER, fixtures.MINT_A, "a"),
            created(fixtures.SIGNER, fixtures.MINT_B, "b"),
            created(fixtures.SIGNER, fixtures.MINT_C, "c"),
            created(fixtures.SPLIT_A, fixtures.SPL_MINT, "d"),
            created(fixtures.SPLIT_A, fixtures.SPLIT_B, "e"),
        ]
    )
    assert [len(c["mints"]) for c in clusters] == [3, 2]
    assert clusters[0]["wallets"] == [fixtures.SIGNER]


def test_min_mints_can_relax_the_filter():
    clusters = build_clusters(
        [
            created(fixtures.SIGNER, fixtures.MINT_A, "a"),
            created(fixtures.SPLIT_A, fixtures.MINT_B, "b"),
        ],
        min_mints=1,
    )
    assert len(clusters) == 2


# -- CLI -------------------------------------------------------------------
class FakeRpc:
    """Stands in for the RPC client so the command runs offline."""

    txs: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    def signatures(self, wallet, limit=200):
        return [
            {"signature": sig, "slot": 1, "blockTime": tx.get("blockTime")}
            for sig, tx in self.txs.items()
        ]

    def transaction(self, signature):
        return self.txs[signature]


def _cluster_args(**overrides):
    base = dict(
        wallet="wallet",
        limit=10,
        min_mints=2,
        max_mints=25,
        max_edges=25,
        out=None,
        json=False,
        rpc="http://localhost",
        pause=0.0,
        retries=0,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_cli_prints_nothing_for_a_control_wallet():
    FakeRpc.txs = {"one": fixtures.single_create_tx(fixtures.MINT_A)}
    out = io.StringIO()
    original = cli.Rpc
    cli.Rpc = FakeRpc
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.cmd_cluster(_cluster_args())
    finally:
        cli.Rpc = original

    assert code == 0
    assert "No cluster above the threshold." in out.getvalue()


def test_cli_json_lists_a_two_mint_cluster():
    FakeRpc.txs = {
        "one": fixtures.single_create_tx(fixtures.MINT_A),
        "two": fixtures.single_create_tx(fixtures.MINT_B),
    }
    out = io.StringIO()
    original = cli.Rpc
    cli.Rpc = FakeRpc
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.cmd_cluster(_cluster_args(json=True))
    finally:
        cli.Rpc = original

    assert code == 0
    payload = json.loads(out.getvalue())
    assert payload["cluster_count"] == 1
    assert payload["scanned_transactions"] == 2
    assert set(payload["clusters"][0]["mints"]) == {fixtures.MINT_A, fixtures.MINT_B}
    assert payload["edge_counts"] == {"created": 2}
