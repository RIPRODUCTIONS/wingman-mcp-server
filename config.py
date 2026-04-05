"""
Configuration for x402 MCP server.
All runtime-configurable values live here. Loaded from environment / .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from mcp_server directory or shared-infra root
_env_path = Path(__file__).parent / ".env"
if not _env_path.exists():
    _env_path = Path(__file__).parent.parent / ".env"
load_dotenv(_env_path, override=False)

# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
# "base-sepolia" = testnet (default, no real money)
# "base"         = mainnet (real USDC)
NETWORK: str = os.environ.get("NETWORK", "base-sepolia")

USDC_ADDRESSES = {
    "base-sepolia": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "base":         "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
}

# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------
# Set to "false" to skip payment verification (dev/test mode)
REQUIRE_PAYMENT: bool = os.environ.get("REQUIRE_PAYMENT", "false").lower() == "true"

# Our receive address — overridden by WALLET_ADDRESS env var after wallet init
WALLET_ADDRESS: str = os.environ.get("WALLET_ADDRESS", "")

# ---------------------------------------------------------------------------
# Prices (USD strings — x402 converts to atomic USDC)
# ---------------------------------------------------------------------------
PRICES = {
    "image_gen":      "$0.10",
    "chat":           "$0.002",
    "scrape":         "$0.03",
    "seo_audit":      "$0.05",
    "content_gen":    "$0.01",
}

# ---------------------------------------------------------------------------
# Service endpoints
# ---------------------------------------------------------------------------
COMFYUI_URL:  str = os.environ.get("COMFYUI_URL",  "http://localhost:8188")
OLLAMA_URL:   str = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
LITELLM_URL:  str = os.environ.get("LITELLM_URL",  "http://localhost:4000")

# Default LLM model.
# LiteLLM proxy uses "llama3.1-8b" (no colon); Ollama native uses "llama3.1:8b".
# The llm service handles the mapping automatically.
DEFAULT_LLM_MODEL: str = os.environ.get("DEFAULT_LLM_MODEL", "llama3.1:8b")

# ---------------------------------------------------------------------------
# ComfyUI model filenames (confirmed from disk)
# ---------------------------------------------------------------------------
FLUX_DIFFUSION_MODEL: str = "flux1-schnell.safetensors"
FLUX_CLIP1:           str = "clip_l.safetensors"
FLUX_CLIP2:           str = "t5xxl_fp8_e4m3fn.safetensors"
FLUX_VAE:             str = "ae.safetensors"

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
PORT: int = int(os.environ.get("PORT", "8402"))

# SQLite path for request/revenue logging
DB_PATH: str = os.environ.get("DB_PATH", str(Path(__file__).parent / "data" / "mcp_server.db"))

# Wallet key file (never committed)
WALLET_KEY_FILE: str = os.environ.get(
    "WALLET_KEY_FILE",
    str(Path(__file__).parent / "data" / "wallet.json")
)

# x402 facilitator — default is the public one run by Coinbase
FACILITATOR_URL: str = os.environ.get("FACILITATOR_URL", "https://x402.org/facilitator")
