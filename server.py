"""
x402 MCP Server — AI compute services for USDC on Base L2.

Endpoints (all POST, require payment when REQUIRE_PAYMENT=true):
  /api/generate-image    $0.10 — Flux Schnell via ComfyUI
  /api/chat              $0.002 — LLM via Ollama/LiteLLM
  /api/scrape            $0.03  — web scraping + extraction
  /api/seo-audit         $0.05  — SEO analysis
  /api/generate-content  $0.01  — content generation

Free endpoints:
  GET /health
  GET /.well-known/x402
  GET /stats

Run:
  uvicorn mcp_server.server:app --port 8402 --host 0.0.0.0
"""
import base64
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import config
from . import db
from .wallet import load_address
from .services import image_gen, llm as llm_service, scraper, seo, content as content_service

# x402 middleware
from x402.fastapi.middleware import require_payment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("mcp_server")


# ---------------------------------------------------------------------------
# Lifespan: init DB and wallet on startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    address = load_address()
    config.WALLET_ADDRESS = address
    log.info("=== x402 MCP Server ===")
    log.info("Wallet:        %s", address)
    log.info("Network:       %s", config.NETWORK)
    log.info("Payment gate:  %s", config.REQUIRE_PAYMENT)
    log.info("Facilitator:   %s", config.FACILITATOR_URL)
    for svc, price in config.PRICES.items():
        log.info("  %-20s %s", svc, price)
    yield


app = FastAPI(
    title="x402 MCP Server",
    description="AI compute services — pay per call in USDC on Base L2",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*", "X-PAYMENT", "X-PAYMENT-RESPONSE"],
    expose_headers=["X-PAYMENT-RESPONSE"],
)


# ---------------------------------------------------------------------------
# Payment middleware factory — applied conditionally
# ---------------------------------------------------------------------------

def _payment_middleware(service_key: str, path: str, description: str):
    """Return x402 payment middleware if REQUIRE_PAYMENT is true, else passthrough."""
    if not config.REQUIRE_PAYMENT:
        # No-op middleware: just calls next handler
        async def passthrough(request: Request, call_next):
            return await call_next(request)
        return passthrough

    return require_payment(
        price=config.PRICES[service_key],
        pay_to_address=config.WALLET_ADDRESS or "0x0000000000000000000000000000000000000000",
        path=path,
        description=description,
        network=config.NETWORK,
        facilitator_config={"url": config.FACILITATOR_URL},
    )


# Register payment middleware for each paid endpoint
# FastAPI processes middleware in reverse-registration order.
# We register after startup so WALLET_ADDRESS is populated.

@app.middleware("http")
async def payment_router(request: Request, call_next):
    """Route payment middleware based on path."""
    if not config.REQUIRE_PAYMENT:
        return await call_next(request)

    # Lazy-init address (populated in lifespan but middleware registered before startup)
    pay_to = config.WALLET_ADDRESS
    if not pay_to:
        pay_to = load_address()
        config.WALLET_ADDRESS = pay_to

    _paid_routes = {
        "/api/generate-image":   ("image_gen",   config.PRICES["image_gen"],   "Flux Schnell image generation"),
        "/api/chat":             ("chat",         config.PRICES["chat"],        "LLM chat completion (Ollama)"),
        "/api/scrape":           ("scrape",       config.PRICES["scrape"],      "Web scraping + data extraction"),
        "/api/seo-audit":        ("seo_audit",    config.PRICES["seo_audit"],   "SEO audit"),
        "/api/generate-content": ("content_gen",  config.PRICES["content_gen"], "Content generation"),
    }

    path = request.url.path
    if path not in _paid_routes:
        return await call_next(request)

    _, price, description = _paid_routes[path]

    mw = require_payment(
        price=price,
        pay_to_address=pay_to,
        path=path,
        description=description,
        network=config.NETWORK,
        facilitator_config={"url": config.FACILITATOR_URL},
    )
    return await mw(request, call_next)


# ---------------------------------------------------------------------------
# Helper: extract payment info from request state for logging
# ---------------------------------------------------------------------------

def _payer_from_request(request: Request) -> tuple[str | None, float | None]:
    """Extract payer address and amount from x402 state (set by middleware)."""
    try:
        reqs = getattr(request.state, "payment_details", None)
        if reqs is None:
            return None, None
        payer = getattr(getattr(request.state, "verify_response", None), "payer", None)
        amount_str = getattr(reqs, "max_amount_required", "0")
        amount_usd = int(amount_str) / 1_000_000  # USDC has 6 decimals
        return payer, amount_usd
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class ImageGenRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    width:  int = Field(default=1024, ge=64,  le=2048)
    height: int = Field(default=1024, ge=64,  le=2048)
    steps:  int = Field(default=4,    ge=1,   le=8)


class ChatRequest(BaseModel):
    messages:   list[dict] = Field(..., min_length=1)
    model:      Optional[str] = None
    max_tokens: int = Field(default=1024, ge=1, le=4096)


class ScrapeRequest(BaseModel):
    url:            str = Field(..., min_length=7)
    extract_fields: Optional[list[str]] = None


class SEOAuditRequest(BaseModel):
    url: str = Field(..., min_length=7)


class ContentRequest(BaseModel):
    type:               str = Field(..., description="blog_post | social_caption | script | email | product_description")
    topic:              str = Field(..., min_length=1, max_length=500)
    length:             str = Field(default="medium", description="short | medium | long")
    extra_instructions: str = Field(default="", max_length=500)


# ---------------------------------------------------------------------------
# Free endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "network": config.NETWORK,
        "require_payment": config.REQUIRE_PAYMENT,
        "wallet": config.WALLET_ADDRESS,
    }


@app.get("/.well-known/x402")
async def x402_discovery():
    """x402 discovery endpoint — lists all paid routes and their prices."""
    base_url = "http://localhost:8402"
    routes = []
    for path, (svc, price, desc) in {
        "/api/generate-image":   ("image_gen",  config.PRICES["image_gen"],  "Flux Schnell image generation via ComfyUI"),
        "/api/chat":             ("chat",        config.PRICES["chat"],       "LLM chat completion via Ollama"),
        "/api/scrape":           ("scrape",      config.PRICES["scrape"],     "Web scraping and data extraction"),
        "/api/seo-audit":        ("seo_audit",   config.PRICES["seo_audit"],  "Full SEO audit"),
        "/api/generate-content": ("content_gen", config.PRICES["content_gen"],"AI content generation"),
    }.items():
        routes.append({
            "path":        path,
            "method":      "POST",
            "service":     svc,
            "price":       price,
            "network":     config.NETWORK,
            "description": desc,
            "resource":    f"{base_url}{path}",
        })

    return {
        "x402_version": 1,
        "pay_to":   config.WALLET_ADDRESS,
        "network":  config.NETWORK,
        "routes":   routes,
    }


@app.get("/stats")
async def stats():
    """Revenue and usage statistics."""
    return db.get_stats()


# ---------------------------------------------------------------------------
# Paid endpoints
# ---------------------------------------------------------------------------

@app.post("/api/generate-image")
async def api_generate_image(body: ImageGenRequest, request: Request):
    t0 = time.monotonic()
    payer, amount_usd = _payer_from_request(request)

    try:
        png_bytes = await image_gen.generate_image(
            prompt=body.prompt,
            width=body.width,
            height=body.height,
            steps=body.steps,
        )
    except RuntimeError as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("image_gen", 503, payer, amount_usd, ms, str(e))
        return JSONResponse({"error": str(e), "service": "ComfyUI"}, status_code=503)
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("image_gen", 500, payer, amount_usd, ms, str(e))
        log.exception("image_gen unexpected error")
        return JSONResponse({"error": "Internal error"}, status_code=500)

    ms = int((time.monotonic() - t0) * 1000)
    db.log_request("image_gen", 200, payer, amount_usd, ms)

    encoded = base64.b64encode(png_bytes).decode()
    return JSONResponse({
        "image_base64": encoded,
        "content_type": "image/png",
        "width":        body.width,
        "height":       body.height,
        "prompt":       body.prompt,
        "duration_ms":  ms,
    })


@app.post("/api/chat")
async def api_chat(body: ChatRequest, request: Request):
    t0 = time.monotonic()
    payer, amount_usd = _payer_from_request(request)

    try:
        result = await llm_service.chat(
            messages=body.messages,
            model=body.model,
            max_tokens=body.max_tokens,
        )
    except RuntimeError as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("chat", 503, payer, amount_usd, ms, str(e))
        return JSONResponse({"error": str(e), "service": "Ollama/LiteLLM"}, status_code=503)
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("chat", 500, payer, amount_usd, ms, str(e))
        log.exception("chat unexpected error")
        return JSONResponse({"error": "Internal error"}, status_code=500)

    ms = int((time.monotonic() - t0) * 1000)
    db.log_request("chat", 200, payer, amount_usd, ms)
    result["duration_ms"] = ms
    return JSONResponse(result)


@app.post("/api/scrape")
async def api_scrape(body: ScrapeRequest, request: Request):
    t0 = time.monotonic()
    payer, amount_usd = _payer_from_request(request)

    try:
        result = await scraper.scrape(
            url=body.url,
            extract_fields=body.extract_fields,
        )
    except ValueError as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("scrape", 400, payer, amount_usd, ms, str(e))
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("scrape", 503, payer, amount_usd, ms, str(e))
        return JSONResponse({"error": str(e)}, status_code=503)
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("scrape", 500, payer, amount_usd, ms, str(e))
        log.exception("scrape unexpected error")
        return JSONResponse({"error": "Internal error"}, status_code=500)

    ms = int((time.monotonic() - t0) * 1000)
    db.log_request("scrape", 200, payer, amount_usd, ms)
    result["duration_ms"] = ms
    return JSONResponse(result)


@app.post("/api/seo-audit")
async def api_seo_audit(body: SEOAuditRequest, request: Request):
    t0 = time.monotonic()
    payer, amount_usd = _payer_from_request(request)

    try:
        result = await seo.audit(url=body.url)
    except ValueError as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("seo_audit", 400, payer, amount_usd, ms, str(e))
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("seo_audit", 503, payer, amount_usd, ms, str(e))
        return JSONResponse({"error": str(e)}, status_code=503)
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("seo_audit", 500, payer, amount_usd, ms, str(e))
        log.exception("seo_audit unexpected error")
        return JSONResponse({"error": "Internal error"}, status_code=500)

    ms = int((time.monotonic() - t0) * 1000)
    db.log_request("seo_audit", 200, payer, amount_usd, ms)
    result["duration_ms"] = ms
    return JSONResponse(result)


@app.post("/api/generate-content")
async def api_generate_content(body: ContentRequest, request: Request):
    t0 = time.monotonic()
    payer, amount_usd = _payer_from_request(request)

    try:
        result = await content_service.generate(
            content_type=body.type,
            topic=body.topic,
            length=body.length,
            extra_instructions=body.extra_instructions,
        )
    except ValueError as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("content_gen", 400, payer, amount_usd, ms, str(e))
        return JSONResponse({"error": str(e)}, status_code=400)
    except RuntimeError as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("content_gen", 503, payer, amount_usd, ms, str(e))
        return JSONResponse({"error": str(e), "service": "Ollama/LiteLLM"}, status_code=503)
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        db.log_request("content_gen", 500, payer, amount_usd, ms, str(e))
        log.exception("content_gen unexpected error")
        return JSONResponse({"error": "Internal error"}, status_code=500)

    ms = int((time.monotonic() - t0) * 1000)
    db.log_request("content_gen", 200, payer, amount_usd, ms)
    result["duration_ms"] = ms
    return JSONResponse(result)
