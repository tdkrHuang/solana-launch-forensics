"""Read-only forensics for pump.fun style token launches.

The package answers four questions from public chain data alone:

1. Which mints did a wallet create?
2. How fast, and were any created in the same transaction?
3. How did the proceeds leave, and did the payouts repeat a single size?
4. Which mints belong to the same operator, and what is the evidence?

It never guesses intent. It reports signatures, slots and amounts, so the
reader can check every claim against an explorer.
"""

from .analytics import (
    create_count,
    equal_size_outflows,
    funding_inflows,
    pump_invocations,
    signers,
    summarize,
    sweep_count,
    swept_mints,
    system_transfers,
    token_mints_in_tx,
)
from .cluster import build_clusters
from .rpc import Rpc, RpcError

__version__ = "0.2.1"

__all__ = [
    "Rpc",
    "RpcError",
    "build_clusters",
    "create_count",
    "equal_size_outflows",
    "funding_inflows",
    "pump_invocations",
    "signers",
    "summarize",
    "sweep_count",
    "swept_mints",
    "system_transfers",
    "token_mints_in_tx",
    "__version__",
]
