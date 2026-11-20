"""Parsing helpers for Solana transactions returned in ``jsonParsed`` encoding.

The goal is deliberately narrow: turn one transaction into a small set of
facts that are useful when auditing token launches.

* who paid and who signed
* which program ran which instruction (resolved from the log stack)
* which token mints were touched, and how many were created
* how SOL moved between accounts

Nothing here assigns blame. It reports what the chain says.

Two details matter more than they look:

1. Contemporary RPC responses for versioned transactions omit
   ``message.header``. Signers therefore come from the per-account
   ``signer`` flag when it is present.
2. ``Program log:`` lines carry no program id. Log lines must be attributed
   by walking the ``invoke`` / ``success`` stack, otherwise a token program
   logging ``Instruction: InitializeMint2`` gets counted as a pump.fun
   instruction.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterator

PUMP_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ASSOCIATED_TOKEN_PROGRAM = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"

LAMPORTS_PER_SOL = 1_000_000_000

CREATE_INSTRUCTIONS = {"Create", "CreateV2"}
SWEEP_INSTRUCTIONS = {"SweepCreatorFee", "CollectCreatorFeeV2"}


# -- accounts -------------------------------------------------------------
def account_keys(tx: dict) -> list[str]:
    keys = tx["transaction"]["message"]["accountKeys"]
    return [k["pubkey"] if isinstance(k, dict) else k for k in keys]


def signers(tx: dict) -> list[str]:
    """All signing accounts, in account-key order.

    Handles both the modern (per-key ``signer`` flag) and legacy
    (``message.header.numRequiredSignatures``) representations.
    """
    raw = tx["transaction"]["message"]["accountKeys"]
    if raw and isinstance(raw[0], dict) and "signer" in raw[0]:
        return [k["pubkey"] for k in raw if k.get("signer")]

    header = tx["transaction"]["message"].get("header") or {}
    n = header.get("numRequiredSignatures", 1)
    return account_keys(tx)[:n]


def fee_payer(tx: dict) -> str | None:
    keys = account_keys(tx)
    return keys[0] if keys else None


# -- instructions ---------------------------------------------------------
def all_instructions(tx: dict) -> Iterator[dict]:
    """Yield outer instructions first, then inner instructions."""
    yield from tx["transaction"]["message"]["instructions"]
    meta = tx.get("meta") or {}
    for group in meta.get("innerInstructions") or []:
        yield from group.get("instructions") or []


def program_ids(tx: dict) -> list[str]:
    return [ix.get("programId", "") for ix in all_instructions(tx)]


def pump_invocations(tx: dict) -> int:
    """How many times the pump.fun program was entered (outer + inner)."""
    return sum(1 for pid in program_ids(tx) if pid == PUMP_PROGRAM)


def log_messages(tx: dict) -> list[str]:
    return (tx.get("meta") or {}).get("logMessages") or []


def log_events(tx: dict) -> list[dict]:
    """Pair every ``Program log:`` line with the program that emitted it.

    The runtime interleaves ``invoke`` / ``success`` markers, so a simple
    stack walk recovers attribution exactly:

        Program A invoke [1]        stack: [A]
        Program log: Instruction: X  -> A
        Program B invoke [2]        stack: [A, B]
        Program log: Instruction: Y  -> B
        Program B success            stack: [A]

    ``Program log: Instruction:`` lines are normalised to
    ``{"program", "instruction"}``. Other log lines keep their raw text.
    """
    stack: list[str] = []
    events: list[dict] = []

    for line in log_messages(tx):
        if line.startswith("Program ") and " invoke [" in line:
            stack.append(line.split()[1])
            continue

        if line.startswith("Program ") and line.endswith(" success"):
            if stack:
                stack.pop()
            continue

        if line.startswith("Program ") and " consumed " in line:
            continue

        if not line.startswith("Program log: "):
            continue

        body = line[len("Program log: "):]
        owner = stack[-1] if stack else None
        if body.startswith("Instruction: "):
            events.append(
                {
                    "program": owner,
                    "instruction": body[len("Instruction: "):].strip(),
                    "raw": line,
                }
            )
        else:
            events.append({"program": owner, "instruction": None, "raw": line})

    return events


def pump_instruction_names(tx: dict) -> list[str]:
    """pump.fun instruction names in execution order."""
    return [
        e["instruction"]
        for e in log_events(tx)
        if e["program"] == PUMP_PROGRAM and e["instruction"]
    ]


def pump_ops(tx: dict) -> dict[str, int]:
    """Counts per pump.fun instruction name."""
    return dict(Counter(pump_instruction_names(tx)))


def create_count(tx: dict) -> int:
    """Number of token-creation calls.

    pump.fun emits ``Instruction: Create`` or ``Instruction: CreateV2`` once
    per mint. Attribution is by program stack, so the token program's own
    ``InitializeMint2`` is never mistaken for a launch.
    """
    return sum(1 for name in pump_instruction_names(tx) if name in CREATE_INSTRUCTIONS)


def sweep_count(tx: dict) -> int:
    """Number of creator-fee collection calls.

    ``SweepCreatorFee`` and ``CollectCreatorFeeV2`` can only be issued by a
    mint's creator, so a sweep is ownership evidence, not a behavioural
    guess. It is also easily confused with a creation when instructions are
    counted without reading their names.
    """
    return sum(1 for name in pump_instruction_names(tx) if name in SWEEP_INSTRUCTIONS)


def swept_mints(tx: dict) -> list[str]:
    """Mints whose creator fee was collected in this transaction.

    Returns an empty list for transactions that contain no sweep, so the
    caller can use it as a predicate without a second pass over the logs.
    """
    if not sweep_count(tx):
        return []
    return token_mints_in_tx(tx)


# -- tokens ---------------------------------------------------------------
def token_mints_in_tx(tx: dict) -> list[str]:
    """Mints *referenced* by the transaction.

    This is intentionally broader than creation: a fee-sweep transaction
    touches mints it did not create. Use :func:`create_count` to separate
    the two questions.

    pump.fun mints carry a ``pump`` vanity suffix, which makes the first
    heuristic cheap. ``initializeMint`` instructions are also parsed so
    non-pump SPL mints are picked up when the encoding allows it.
    """
    found: dict[str, None] = {}

    for key in account_keys(tx):
        if key.endswith("pump"):
            found[key] = None

    for ix in all_instructions(tx):
        if ix.get("programId") not in (TOKEN_PROGRAM, TOKEN_2022_PROGRAM):
            continue
        parsed = ix.get("parsed")
        if not isinstance(parsed, dict):
            continue
        if parsed.get("type") in {"initializeMint", "initializeMint2"}:
            mint = (parsed.get("info") or {}).get("mint")
            if mint:
                found[mint] = None

    return list(found)


# -- value flow -----------------------------------------------------------
def system_transfers(tx: dict) -> list[dict]:
    """SOL transfers as ``{source, destination, lamports}``."""
    out: list[dict] = []
    for ix in all_instructions(tx):
        if ix.get("programId") != SYSTEM_PROGRAM:
            continue
        parsed = ix.get("parsed")
        if not isinstance(parsed, dict) or parsed.get("type") != "transfer":
            continue
        info = parsed.get("info") or {}
        try:
            lamports = int(info.get("lamports", 0))
        except (TypeError, ValueError):
            continue
        out.append(
            {
                "source": info.get("source"),
                "destination": info.get("destination"),
                "lamports": lamports,
            }
        )
    return out


def funding_inflows(tx: dict) -> list[dict]:
    """SOL transfers into the fee payer from another account.

    A launch wallet is usually funded just before it creates, so the payer is
    a useful link between otherwise unrelated creations. Transfers out of the
    payer are excluded: they say nothing about who controls it.
    """
    payer = fee_payer(tx)
    if not payer:
        return []
    out: list[dict] = []
    for t in system_transfers(tx):
        if t["destination"] != payer or t["source"] == payer:
            continue
        if t["lamports"] <= 0 or not t["source"]:
            continue
        out.append(
            {
                "from": t["source"],
                "to": payer,
                "lamports": t["lamports"],
            }
        )
    return out


def sol_balance_deltas(tx: dict) -> dict[str, int]:
    """Net lamport change per account, from ``meta.pre/postBalances``."""
    meta = tx.get("meta") or {}
    keys = account_keys(tx)
    pre = meta.get("preBalances") or []
    post = meta.get("postBalances") or []
    deltas: dict[str, int] = {}
    for i, key in enumerate(keys):
        if i >= len(pre) or i >= len(post):
            continue
        deltas[key] = deltas.get(key, 0) + (post[i] - pre[i])
    return deltas


def equal_size_outflows(tx: dict, *, min_count: int = 2) -> list[dict]:
    """Groups of transfers leaving a signer with an identical lamport size.

    Scripted payouts tend to round to one number; humans rarely do.
    """
    signer_set = set(signers(tx))
    groups: dict[int, list[str]] = defaultdict(list)
    for t in system_transfers(tx):
        if t["source"] in signer_set and t["lamports"] > 0:
            groups[t["lamports"]].append(t["destination"])

    out = []
    for lamports, dests in groups.items():
        unique = sorted({d for d in dests if d})
        if len(unique) >= min_count:
            out.append(
                {
                    "lamports": lamports,
                    "sol": lamports / LAMPORTS_PER_SOL,
                    "destinations": unique,
                }
            )
    return sorted(out, key=lambda g: -g["lamports"])


# -- summary --------------------------------------------------------------
def summarize(tx: dict) -> dict:
    meta = tx.get("meta") or {}
    mints = token_mints_in_tx(tx)
    names = pump_instruction_names(tx)
    ops = Counter(names)
    creates = sum(ops[n] for n in CREATE_INSTRUCTIONS)
    repeated = {k: v for k, v in ops.items() if v >= 2}

    return {
        "slot": tx.get("slot"),
        "block_time": tx.get("blockTime"),
        "fee_payer": fee_payer(tx),
        "signers": signers(tx),
        "fee_lamports": meta.get("fee"),
        "err": meta.get("err"),
        "pump_invocations": pump_invocations(tx),
        "pump_instructions": names,
        "pump_ops": dict(ops),
        "repeated_ops": repeated,
        "creates": creates,
        "mints": mints,
        "creates_mints": creates >= 2,
        "batches_ops": bool(repeated),
        "transfers": len(system_transfers(tx)),
        "equal_size_outflows": equal_size_outflows(tx),
    }


def format_sol(lamports: int) -> str:
    return f"{lamports / LAMPORTS_PER_SOL:.9f}".rstrip("0").rstrip(".")
