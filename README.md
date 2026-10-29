# Wingman MCP Server — AI Services via x402

Pay-per-call AI services on Base L2 (USDC). No accounts, no subscriptions — agents pay automatically via x402 protocol.

## Pay per call with x402 (no account, no API key)

Three live web verbs answer an unpaid request with HTTP 402 and accept an x402 v2 payment in USDC on Base. Prices are the ones served today by [`/.well-known/x402`](https://agent.wingmanprotocol.com/.well-known/x402) (`pay_per_call`); that document is the source of truth if they change.

| Endpoint | Price per call | Body |
|---|---|---|
| `POST https://agent.wingmanprotocol.com/v1/web_search` | $0.007 | `{"query": "...", "count": 8}` |
| `POST https://agent.wingmanprotocol.com/v1/web_read` | $0.002 | `{"url": "https://..."}` |
| `POST https://agent.wingmanprotocol.com/v1/research` | $0.05 | `{"query": "...", "max_pages": 3}` |

1. **POST** the request with no payment.
2. **Read the 402.** The `PAYMENT-REQUIRED` response header (base64 JSON) carries the price, asset, network and `payTo`.
3. **Retry** the same request with a signed EIP-3009 authorization in the `PAYMENT-SIGNATURE` header. Any x402 v2 client does steps 2 and 3 for you.

Links: [`/.well-known/x402`](https://agent.wingmanprotocol.com/.well-known/x402) · [x402scan listing](https://www.x402scan.com/server/095bda9f-cd94-4930-866e-fc2c270e3717) · MCP endpoint `https://agent.wingmanprotocol.com/mcp` (the same verbs are the `web_search`, `web_read` and `research` tools)

## Services

| Service | Price | Description |
|---------|-------|-------------|
| Image Generation | $0.10 | Flux Schnell via ComfyUI — fast, high quality |
| LLM Chat | $0.002 | Ollama llama3.1 — cheap, fast, private |
| Web Scraping | $0.03 | Structured data extraction from any URL |
| SEO Audit | $0.05 | Full technical SEO analysis, 0-100 score |
| Content Generation | $0.01 | Blog posts, captions, scripts, calendars |

## Quick Start

```bash
# Discovery endpoint
curl https://wingmanprotocol.com/mcp/.well-known/x402

# Free test (no payment required in test mode)
curl -X POST https://wingmanprotocol.com/mcp/api/seo-audit \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# LLM chat
curl -X POST https://wingmanprotocol.com/mcp/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

## x402 Payment

All endpoints accept x402 payments in USDC on Base L2. The `/.well-known/x402` endpoint describes pricing and wallet details.

- **Network:** Base (eip155:8453)
- **Currency:** USDC
- **Facilitator:** x402.org

## Self-Hosted

```bash
pip install fastapi uvicorn httpx x402 beautifulsoup4 stripe
python -m uvicorn mcp_server.server:app --port 8402
```

## Stack

- FastAPI + x402 middleware
- Ollama (local LLM, $0/call)
- ComfyUI + Flux Schnell (local image gen, $0/image)
- SQLite request logging
- Base L2 wallet for USDC settlement

## License

MIT
