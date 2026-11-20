"""Tests for dataset records and the shared edge pipeline."""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fixtures
from launchforensics import dataset as D
from launchforensics.pipeline import collect_edges


def cluster(mints, links, first=1000, last=1600, wallets=("w1",)):
    return {
        "mints": list(mints),
        "wallets": list(wallets),
        "links": dict(links),
        "first_block_time": first,
        "last_block_time": last,
        "edges": [],
    }


# -- confidence ------------------------------------------------------------
def test_sweep_makes_a_cluster_high_confidence():
    assert D.confidence(cluster(["a", "b"], {"created": 2, "swept": 1})) == "high"


def test_two_creations_without_a_sweep_are_medium():
    assert D.confidence(cluster(["a", "b"], {"created": 2})) == "medium"


def test_funding_only_is_low():
    assert D.confidence(cluster(["a", "b"], {"created": 1, "funded": 3})) == "low"


# -- ids -------------------------------------------------------------------
def test_cluster_id_is_stable_and_order_independent():
    one = D.cluster_id({"mints": ["a", "b"]})
    two = D.cluster_id({"mints": ["b", "a"]})
    assert one == two
    assert one.startswith("c") and len(one) == 13


def test_cluster_id_changes_with_a_different_mint():
    assert D.cluster_id({"mints": ["a", "b"]}) != D.cluster_id({"mints": ["a", "c"]})


# -- records ---------------------------------------------------------------
def test_record_computes_the_window_and_keeps_provenance():
    rec = D.record(
        cluster(["a", "b"], {"created": 2, "swept": 1}, first=1000, last=1600),
        seed_wallet="seed",
        scanned=42,
        tool_version="0.2.0",
        limit=200,
        source="unit-test",
    )
    assert rec["window_seconds"] == 600
    assert rec["mint_count"] == 2
    assert rec["confidence"] == "high"
    assert rec["scanned_transactions"] == 42
    assert rec["method"] == "launchforensics 0.2.0 cluster --limit 200"
    assert rec["source"] == "unit-test"


def test_record_without_timestamps_has_a_zero_window():
    rec = D.record(
        cluster(["a", "b"], {"created": 2}, first=None, last=None),
        seed_wallet="seed",
        scanned=1,
        tool_version="0.2.0",
        limit=10,
    )
    assert rec["window_seconds"] == 0
    assert rec["first_block_time"] is None


# -- pipeline --------------------------------------------------------------
class FakeRpc:
    def __init__(self, txs, fail=()):
        self.txs = txs
        self.fail = set(fail)

    def signatures(self, wallet, limit=200):
        return [
            {"signature": sig, "slot": 1, "blockTime": tx.get("blockTime")}
            for sig, tx in self.txs.items()
        ][:limit]

    def transaction(self, signature):
        if signature in self.fail:
            raise RuntimeError("rpc failed")
        return self.txs[signature]


def test_pipeline_collects_creation_edges():
    rpc = FakeRpc({"one": fixtures.single_create_tx(fixtures.MINT_A)})
    scan = collect_edges(rpc, "wallet", limit=10)
    assert scan["scanned"] == 1
    assert scan["failed"] == 0
    assert [e["type"] for e in scan["edges"]] == ["created"]
    assert scan["edges"][0]["mint"] == fixtures.MINT_A
    assert scan["edges"][0]["signature"] == "one"


def test_pipeline_survives_a_failed_transaction():
    rpc = FakeRpc(
        {"one": fixtures.single_create_tx(fixtures.MINT_A), "two": fixtures.single_create_tx(fixtures.MINT_B)},
        fail={"one"},
    )
    errors = []
    scan = collect_edges(rpc, "wallet", limit=10, on_error=lambda sig, exc: errors.append(sig))
    assert scan["failed"] == 1
    assert scan["scanned"] == 1
    assert errors == ["one"]


def test_pipeline_reports_an_empty_wallet():
    scan = collect_edges(FakeRpc({}), "wallet")
    assert scan["requested"] == 0
    assert scan["edges"] == []
    assert scan["stopped_early"] is False
