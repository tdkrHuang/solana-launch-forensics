"""Read-only forensics for pump.fun style token launches.

The package answers three questions from public chain data alone:

1. Which mints did a wallet create?
2. How fast, and were any created in the same transaction?
3. How did the proceeds leave, and did the payouts repeat a single size?

It never guesses intent. It reports signatures, slots and amounts, so the
reader can check every claim against an explorer.
"""

from .analytics import (
    create_count,
    equal_size_outflows,
    pump_invocations,
    signers,
    summarize,
    system_transfers,
    token_mints_in_tx,
)
from .rpc import Rpc, RpcError

__version__ = "0.1.0"

__all__ = [
    "Rpc",
    "RpcError",
    "create_count",
    "equal_size_outflows",
    "pump_invocations",
    "signers",
    "summarize",
    "system_transfers",
    "token_mints_in_tx",
    "__version__",
]
