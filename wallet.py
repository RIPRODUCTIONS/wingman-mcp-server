"""
Wallet management for the x402 MCP server.

Generates a new Ethereum keypair on first run and persists it to
WALLET_KEY_FILE (default: mcp_server/data/wallet.json).

The private key is stored with mode 0o600. Never committed — add
data/wallet.json to .gitignore.

Usage:
    from mcp_server.wallet import get_or_create_wallet
    address, private_key = get_or_create_wallet()
"""
import json
import os
import stat
from pathlib import Path

from eth_account import Account

from . import config


def get_or_create_wallet() -> tuple[str, str]:
    """
    Return (address, private_key_hex).

    Priority:
      1. WALLET_ADDRESS + WALLET_PRIVATE_KEY env vars (CI / secrets manager)
      2. Persisted wallet.json
      3. Generate fresh keypair and persist
    """
    env_addr = os.environ.get("WALLET_ADDRESS", "")
    env_key  = os.environ.get("WALLET_PRIVATE_KEY", "")
    if env_addr and env_key:
        return env_addr, env_key

    key_file = Path(config.WALLET_KEY_FILE)
    key_file.parent.mkdir(parents=True, exist_ok=True)

    if key_file.exists():
        with open(key_file) as f:
            data = json.load(f)
        return data["address"], data["private_key"]

    # Generate new wallet
    Account.enable_unaudited_hdwallet_features()
    acct = Account.create()
    private_key = acct.key.hex()
    address     = acct.address

    payload = {
        "address":     address,
        "private_key": private_key,
        "network":     config.NETWORK,
        "warning":     "Keep private_key secret. Never commit this file.",
    }
    with open(key_file, "w") as f:
        json.dump(payload, f, indent=2)

    # Restrict permissions: owner read/write only
    os.chmod(key_file, stat.S_IRUSR | stat.S_IWUSR)

    return address, private_key


def load_address() -> str:
    """Return just the wallet address (no key material exposed)."""
    address, _ = get_or_create_wallet()
    return address
