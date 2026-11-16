"""Minimal Solana JSON-RPC client built on the standard library only.

No API key, no third-party packages. Defaults to the public mainnet endpoint,
which is rate limited -- point ``--rpc`` at your own node for anything serious.
"""

from __future__ import annotations

import json
import os
import random
import time
import urllib.error
import urllib.request

DEFAULT_RPC = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
USER_AGENT = "solana-launch-forensics/0.1"


class RpcError(RuntimeError):
    """Raised when the node returns a JSON-RPC error object."""

    def __init__(self, method: str, error: dict):
        self.method = method
        self.error = error
        super().__init__(f"{method}: {error.get('message', error)}")


class Rpc:
    def __init__(
        self,
        url: str = DEFAULT_RPC,
        *,
        pause: float = 0.35,
        retries: int = 6,
        timeout: float = 45.0,
    ) -> None:
        self.url = url
        self.pause = pause
        self.retries = retries
        self.timeout = timeout
        self._id = 0

    # -- transport ---------------------------------------------------------
    def _post(self, body: bytes) -> dict:
        req = urllib.request.Request(
            self.url,
            data=body,
            headers={
                "content-type": "application/json",
                "user-agent": USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)

    def call(self, method: str, params: list):
        self._id += 1
        body = json.dumps(
            {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
        ).encode()

        delay = 0.8
        last_error: Exception | None = None

        for _ in range(self.retries):
            try:
                payload = self._post(body)
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in RETRYABLE_STATUS:
                    raise
                time.sleep(delay + random.random() * 0.4)
                delay = min(delay * 2, 20.0)
                continue
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last_error = exc
                time.sleep(delay + random.random() * 0.4)
                delay = min(delay * 2, 20.0)
                continue

            if payload.get("error"):
                err = payload["error"]
                # -32005 = node is behind / rate limited; worth retrying
                if err.get("code") == -32005:
                    last_error = RpcError(method, err)
                    time.sleep(delay)
                    delay = min(delay * 2, 20.0)
                    continue
                raise RpcError(method, err)

            time.sleep(self.pause)
            return payload["result"]

        raise RuntimeError(f"{method}: retries exhausted ({last_error})")

    # -- convenience -------------------------------------------------------
    def signatures(
        self,
        address: str,
        *,
        limit: int = 1000,
        before: str | None = None,
        until: str | None = None,
        commitment: str = "confirmed",
    ) -> list[dict]:
        opts: dict = {"limit": min(limit, 1000), "commitment": commitment}
        if before:
            opts["before"] = before
        if until:
            opts["until"] = until
        return self.call("getSignaturesForAddress", [address, opts])

    def transaction(self, signature: str, *, commitment: str = "confirmed") -> dict | None:
        return self.call(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "maxSupportedTransactionVersion": 1,
                    "commitment": commitment,
                },
            ],
        )

    def account_info(self, address: str, *, commitment: str = "confirmed") -> dict | None:
        res = self.call(
            "getAccountInfo",
            [address, {"encoding": "jsonParsed", "commitment": commitment}],
        )
        return res.get("value") if res else None
