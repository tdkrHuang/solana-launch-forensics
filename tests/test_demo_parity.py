"""The browser demo must parse transactions exactly like the CLI.

Two implementations of the same rule drift silently, and the demo is the one
prospect-facing surface where a wrong number is visible without a caveat. This
test pins the port to the Python implementation on real mainnet transactions:
one creation, one fee sweep.

Skipped when Node is unavailable, since the demo is not part of the Python
package.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

from launchforensics import analytics as A

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "demo_txs.json"
SCRIPT = ROOT / "tools" / "demo_parity_check.mjs"


@pytest.fixture(scope="module")
def node_available() -> None:
    if shutil.which("node") is None:
        pytest.skip("node is not installed")


def _python_view(tx: dict) -> dict:
    info = A.summarize(tx)
    return {
        "fee_payer": info["fee_payer"],
        "creates": info["creates"],
        "mints": sorted(info["mints"]),
        "swept": sorted(A.swept_mints(tx)),
        "funding": sorted([[f["from"], f["to"], f["lamports"]] for f in A.funding_inflows(tx)]),
        "pump": info["pump_instructions"],
        "created_edges": sorted(info["mints"]) if info["creates"] else [],
    }


def test_demo_matches_cli(node_available: None) -> None:
    txs = json.loads(FIXTURE.read_text(encoding="utf-8"))
    proc = subprocess.run(
        ["node", str(SCRIPT), str(FIXTURE)],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    js = json.loads(proc.stdout)

    assert len(js) == len(txs)
    for tx, got in zip(txs, js):
        want = _python_view(tx)
        for field in ("fee_payer", "creates", "mints", "swept", "funding", "pump"):
            assert got[field] == want[field], (field, got[field], want[field])

        created = [e["mint"] for e in got["edges"] if e["type"] == "created"]
        swept = [e["mint"] for e in got["edges"] if e["type"] == "swept"]
        assert sorted(created) == want["created_edges"]
        assert sorted(swept) == want["swept"]


def test_fixture_covers_both_events() -> None:
    txs = json.loads(FIXTURE.read_text(encoding="utf-8"))
    views = [_python_view(tx) for tx in txs]
    assert any(v["creates"] > 0 for v in views), "fixture has no creation transaction"
    assert any(v["swept"] for v in views), "fixture has no fee-sweep transaction"
