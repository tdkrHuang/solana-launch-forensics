"""Fixtures shaped like real ``jsonParsed`` responses from Solana RPC.

Values are trimmed to the fields the parser reads. Addresses are realistic
base58 strings so length-based logic is exercised.

``create_tx_v0`` mirrors a genuine pump.fun ``CreateV2`` response captured
from mainnet: versioned transaction, no ``message.header``, and the
Token-2022 program logging its own ``InitializeMint2`` inside the pump call.
"""

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ASSOCIATED_TOKEN_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"

SIGNER = "GtTg74ZpUbUgfNuQHLkVu4KWHxtfVzBWJp9k5S6c4W14"
SPLIT_A = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
SPLIT_B = "3Kz7bW4kZ1oQ2mHcT8yNv5rLpD6sJfA9uE2xC7hRmLnQ"
SPLIT_C = "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj"

MINT_A = "EGX8MJT8wd3GacNckpMYhFjomhDpPvfAz2sj84Wjpump"
MINT_B = "2ZZhunwtYTQ6C8aXuzkRwjAAK6mt3QAWnc5fHcm4pump"
MINT_C = "2GoDADTFmh8p3yrGt6SWyK7HyWHZQ8YYpMBocUdjpump"

SPL_MINT = "So11111111111111111111111111111111111111112"


def _keys(*pubkeys, signer_flags=None):
    flags = signer_flags or [i == 0 for i in range(len(pubkeys))]
    return [
        {"pubkey": p, "signer": flags[i], "writable": True, "source": "transaction"}
        for i, p in enumerate(pubkeys)
    ]


def batch_create_tx(creates: int = 7, mints=None, split_sol: float = 0.486609) -> dict:
    """One transaction that creates several pump mints and splits SOL evenly."""
    mints = mints or [MINT_A, MINT_B, MINT_C]
    lamports = int(split_sol * 1_000_000_000)
    destinations = [SPLIT_A, SPLIT_B, SPLIT_C]

    instructions = [
        {"programId": PUMP_PROGRAM, "accounts": [], "data": "", "stackHeight": None}
        for _ in range(creates)
    ] + [
        {
            "programId": SYSTEM_PROGRAM,
            "parsed": {
                "type": "transfer",
                "info": {"source": SIGNER, "destination": d, "lamports": lamports},
            },
            "program": "system",
            "stackHeight": None,
        }
        for d in destinations
    ]

    logs = ["Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]"]
    logs += ["Program log: Instruction: Create" for _ in range(creates)]
    logs += ["Program log: Instruction: Buy", "Program 11111111111111111111111111111111 invoke [1]"]
    logs += ["Program log: Instruction: Transfer" for _ in destinations]

    pre = [10_000_000_000] + [0] * (len(destinations) + len(mints))
    post = [10_000_000_000 - lamports * len(destinations) - 5000] + [lamports] * len(destinations) + [0] * len(mints)

    return {
        "slot": 312_004_881,
        "blockTime": 1_763_268_569,
        "transaction": {
            "message": {
                "header": {"numRequiredSignatures": 1, "numReadonlySignedAccounts": 0, "numReadonlyUnsignedAccounts": 1},
                "accountKeys": _keys(SIGNER, *destinations, *mints),
                "instructions": instructions,
            }
        },
        "meta": {
            "fee": 5000,
            "err": None,
            "preBalances": pre,
            "postBalances": post,
            "innerInstructions": [],
            "logMessages": logs,
        },
    }


def create_and_buy_tx(created: str = MINT_A, bought: str = MINT_B) -> dict:
    """A real shape that used to break attribution: create one mint, buy another.

    Both mints appear in the account list, so anything that counts pump-suffixed
    keys as creations credits the buyer with a mint it never created.
    """
    tx = single_create_tx(created)
    tx["transaction"]["message"]["accountKeys"] = _keys(SIGNER, created, bought)
    tx["meta"]["preBalances"] = [1_000_000_000, 0, 0]
    tx["meta"]["postBalances"] = [999_995_000, 0, 0]
    tx["meta"]["logMessages"] = tx["meta"]["logMessages"] + [
        f"Program {PUMP_PROGRAM} invoke [1]",
        "Program log: Instruction: Buy",
        f"Program {PUMP_PROGRAM} success",
    ]
    return tx


def create_tx_v0() -> dict:
    """A real-shaped pump.fun CreateV2 transaction.

    No ``message.header`` (versioned tx), two signers (fee payer plus the
    mint keypair), and Token-2022 logging ``InitializeMint2`` inside the
    pump.fun invoke. ``create_count`` must return 1, not 2.
    """
    return {
        "slot": 312_004_851,
        "blockTime": 1_763_268_569,
        "version": 0,
        "transaction": {
            "message": {
                "accountKeys": _keys(
                    SIGNER, MINT_A, SYSTEM_PROGRAM, PUMP_PROGRAM, TOKEN_2022_PROGRAM,
                    signer_flags=[True, True, False, False, False],
                ),
                "instructions": [
                    {"programId": PUMP_PROGRAM, "accounts": [], "data": "", "stackHeight": None}
                ],
                "recentBlockhash": "8fJ1XKz6Yb3kQp2mNv7rLd5sTfA9uE2xC7hRmLnQwZa",
            },
            "signatures": ["5WSkEpd38MgG4FnnpNyRq7pq5MHsi3k27F5U8masNapz"],
        },
        "meta": {
            "fee": 5000,
            "err": None,
            "preBalances": [10_000_000_000, 0, 0, 0, 0],
            "postBalances": [9_997_000_000, 0, 0, 0, 0],
            "innerInstructions": [],
            "logMessages": [
                f"Program {SYSTEM_PROGRAM} invoke [1]",
                f"Program {SYSTEM_PROGRAM} success",
                f"Program {PUMP_PROGRAM} invoke [1]",
                "Program log: Instruction: CreateV2",
                f"Program {SYSTEM_PROGRAM} invoke [2]",
                f"Program {SYSTEM_PROGRAM} success",
                f"Program {TOKEN_2022_PROGRAM} invoke [2]",
                "Program log: MetadataPointerInstruction::Initialize",
                f"Program {TOKEN_2022_PROGRAM} success",
                f"Program {TOKEN_2022_PROGRAM} invoke [2]",
                "Program log: Instruction: InitializeMint2",
                f"Program {TOKEN_2022_PROGRAM} success",
                f"Program {ASSOCIATED_TOKEN_PROGRAM} invoke [2]",
                "Program log: Create",
                "Program log: Initialize the associated token account",
                f"Program {ASSOCIATED_TOKEN_PROGRAM} success",
                f"Program {PUMP_PROGRAM} success",
            ],
        },
    }


def sweep_tx(count: int = 7) -> dict:
    """Creator-fee sweep across several mints in a single transaction.

    This is *not* a launch: no ``Create`` instruction appears. It matters
    because it proves one wallet controls the creator-fee accounts of every
    mint referenced.
    """
    mints = [MINT_A, MINT_B, MINT_C][: min(count, 3)]
    instructions = [
        {"programId": PUMP_PROGRAM, "accounts": [], "data": "", "stackHeight": None}
        for _ in range(count)
    ]

    logs = []
    for _ in range(count):
        logs += [f"Program {PUMP_PROGRAM} invoke [1]", "Program log: Instruction: SweepCreatorFee"]
        logs += [f"Program {PUMP_PROGRAM} invoke [2]", f"Program {PUMP_PROGRAM} success"]
        logs += [f"Program {PUMP_PROGRAM} success"]

    return {
        "slot": 312_006_100,
        "blockTime": 1_763_270_181,
        "version": 0,
        "transaction": {
            "message": {
                "accountKeys": _keys(SIGNER, *mints),
                "instructions": instructions,
                "recentBlockhash": "4dQ2mNv7rLd5sTfA9uE2xC7hRmLnQwZa8fJ1XKz6Yb3k",
            },
            "signatures": ["zWcwg1pBsstXjKUw3oEZrqz4hpsYd5CCkY5kvksTHFJ"],
        },
        "meta": {
            "fee": 32_283,
            "err": None,
            "preBalances": [1_000_000_000] + [0] * len(mints),
            "postBalances": [1_000_000_000 - 32_283] + [0] * len(mints),
            "innerInstructions": [],
            "logMessages": logs,
        },
    }


def _initialize_mint_ix(mint: str) -> dict:
    """The token-program instruction that actually creates a mint."""
    return {
        "programId": TOKEN_PROGRAM,
        "parsed": {"type": "initializeMint", "info": {"mint": mint, "decimals": 6, "mintAuthority": SIGNER}},
        "program": "spl-token",
        "stackHeight": 2,
    }


def single_create_tx(mint: str = MINT_A) -> dict:
    return {
        "slot": 312_004_890,
        "blockTime": 1_763_268_600,
        "transaction": {
            "message": {
                "header": {"numRequiredSignatures": 1, "numReadonlySignedAccounts": 0, "numReadonlyUnsignedAccounts": 1},
                "accountKeys": _keys(SIGNER, mint),
                "instructions": [
                    {"programId": PUMP_PROGRAM, "accounts": [], "data": "", "stackHeight": None}
                ],
            }
        },
        "meta": {
            "fee": 5000,
            "err": None,
            "preBalances": [1_000_000_000, 0],
            "postBalances": [999_995_000, 0],
            "innerInstructions": [
                {"index": 0, "instructions": [_initialize_mint_ix(mint)]}
            ],
            "logMessages": [
                f"Program {PUMP_PROGRAM} invoke [1]",
                "Program log: Instruction: Create",
                f"Program {TOKEN_PROGRAM} invoke [2]",
                "Program log: Instruction: InitializeMint",
                f"Program {TOKEN_PROGRAM} success",
                f"Program {PUMP_PROGRAM} success",
            ],
        },
    }


def spl_initialize_mint_tx(mint: str = SPL_MINT) -> dict:
    return {
        "slot": 1,
        "blockTime": 1_700_000_000,
        "transaction": {
            "message": {
                "header": {"numRequiredSignatures": 1, "numReadonlySignedAccounts": 0, "numReadonlyUnsignedAccounts": 1},
                "accountKeys": _keys(SIGNER, mint),
                "instructions": [
                    {
                        "programId": TOKEN_PROGRAM,
                        "parsed": {
                            "type": "initializeMint",
                            "info": {"mint": mint, "decimals": 9, "mintAuthority": SIGNER},
                        },
                        "program": "spl-token",
                        "stackHeight": None,
                    }
                ],
            }
        },
        "meta": {
            "fee": 5000,
            "err": None,
            "preBalances": [0, 0],
            "postBalances": [0, 0],
            "innerInstructions": [],
            "logMessages": [],
        },
    }
