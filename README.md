# Wingman MCP Server — AI Services via x402

Pay-per-call AI services on Base L2 (USDC). No accounts, no subscriptions — agents pay automatically via x402 protocol.

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
