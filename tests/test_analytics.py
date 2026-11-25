import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import fixtures
from launchforensics import analytics as A


# -- accounts -------------------------------------------------------------
def test_signers_from_header_when_present():
    assert A.signers(fixtures.batch_create_tx()) == [fixtures.SIGNER]


def test_signers_from_flags_when_header_missing():
    tx = fixtures.create_tx_v0()
    assert A.signers(tx) == [fixtures.SIGNER, fixtures.MINT_A]


def test_fee_payer_is_first_key():
    assert A.fee_payer(fixtures.batch_create_tx()) == fixtures.SIGNER


# -- log attribution ------------------------------------------------------
def test_log_events_attributes_to_invoking_program():
    tx = fixtures.create_tx_v0()
    owned = [(e["program"], e["instruction"]) for e in A.log_events(tx) if e["instruction"]]
    pump_ops = [i for p, i in owned if p == fixtures.PUMP_PROGRAM]
    token_ops = [i for p, i in owned if p == fixtures.TOKEN_2022_PROGRAM]
    assert pump_ops == ["CreateV2"]
    assert "InitializeMint2" in token_ops


def test_create_count_ignores_token_program_initialize_mint():
    tx = fixtures.create_tx_v0()
    assert A.create_count(tx) == 1


def test_create_count_handles_create_v2():
    tx = fixtures.batch_create_tx(creates=7)
    assert A.create_count(tx) == 7


def test_create_count_is_zero_without_logs():
    tx = fixtures.single_create_tx()
    tx["meta"]["logMessages"] = []
    assert A.create_count(tx) == 0


def test_pump_ops_counts_repeats():
    tx = fixtures.sweep_tx(7)
    assert A.pump_ops(tx)["SweepCreatorFee"] == 7
    assert A.create_count(tx) == 0


# -- tokens ---------------------------------------------------------------
def test_token_mints_picks_up_pump_suffix():
    mints = A.token_mints_in_tx(fixtures.batch_create_tx())
    assert len(mints) == 3
    assert all(m.endswith("pump") for m in mints)


def test_token_mints_picks_up_initialize_mint():
    assert A.token_mints_in_tx(fixtures.spl_initialize_mint_tx()) == [fixtures.SPL_MINT]


# -- value flow -----------------------------------------------------------
def test_system_transfers_extracts_lamports():
    transfers = A.system_transfers(fixtures.batch_create_tx(split_sol=0.486609))
    assert len(transfers) == 3
    assert all(t["lamports"] == 486_609_000 for t in transfers)


def test_equal_size_outflows_groups_identical_amounts():
    groups = A.equal_size_outflows(fixtures.batch_create_tx(split_sol=0.486609))
    assert len(groups) == 1
    assert groups[0]["sol"] == 0.486609
    assert len(groups[0]["destinations"]) == 3


def test_equal_size_outflows_ignores_single_destination():
    tx = fixtures.batch_create_tx()
    transfers = [
        ix for ix in tx["transaction"]["message"]["instructions"]
        if ix.get("programId") == fixtures.SYSTEM_PROGRAM
    ]
    tx["transaction"]["message"]["instructions"] = transfers[:1]
    assert A.equal_size_outflows(tx) == []


def test_equal_size_outflows_ignores_non_signer_source():
    tx = fixtures.batch_create_tx()
    for ix in tx["transaction"]["message"]["instructions"]:
        if ix.get("parsed", {}).get("type") == "transfer":
            ix["parsed"]["info"]["source"] = fixtures.SPLIT_A
    assert A.equal_size_outflows(tx) == []


def test_sol_balance_deltas():
    deltas = A.sol_balance_deltas(fixtures.batch_create_tx(split_sol=0.1))
    assert deltas[fixtures.SIGNER] < 0
    assert deltas[fixtures.SPLIT_A] == 100_000_000


# -- summary --------------------------------------------------------------
def test_repeated_create_logs_do_not_make_a_creation():
    # Seven Create lines, no token program InitializeMint: nothing was created.
    info = A.summarize(fixtures.batch_create_tx(creates=7))
    assert info["creates_mints"] is False
    assert info["creates"] == 7
    assert info["created_mints"] == []
    assert info["pump_invocations"] == 7
    assert info["err"] is None


def test_bought_mint_in_a_create_tx_is_not_created():
    info = A.summarize(fixtures.create_and_buy_tx())
    assert info["creates"] == 1
    assert info["created_mints"] == [fixtures.MINT_A]
    assert set(info["mints"]) == {fixtures.MINT_A, fixtures.MINT_B}


def test_summarize_flags_repeated_ops_without_creates():
    info = A.summarize(fixtures.sweep_tx(7))
    assert info["creates_mints"] is False
    assert info["batches_ops"] is True
    assert info["repeated_ops"] == {"SweepCreatorFee": 7}


def test_summarize_single_is_quiet():
    info = A.summarize(fixtures.single_create_tx())
    assert info["creates_mints"] is False
    assert info["batches_ops"] is False
    assert info["creates"] == 1
    assert info["created_mints"] == [fixtures.MINT_A]


def test_format_sol_trims_trailing_zeros():
    assert A.format_sol(486_609_000) == "0.486609"
    assert A.format_sol(1_000_000_000) == "1"
    assert A.format_sol(1) == "0.000000001"


def test_summarize_is_json_serializable():
    assert json.dumps(A.summarize(fixtures.batch_create_tx()), default=str)
