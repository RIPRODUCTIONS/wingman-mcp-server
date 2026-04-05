"""
LLM inference via LiteLLM proxy (localhost:4000) with Ollama fallback.

LiteLLM on :4000 is already running as a LaunchAgent and can route to
any Ollama model. We hit it first; if down, fall back to Ollama directly.

Returns: ChatCompletion-style response dict.
"""
import httpx

from .. import config


async def chat(
    messages: list[dict],
    model: str | None = None,
    max_tokens: int = 1024,
) -> dict:
    """
    Send chat completion request.

    Args:
        messages:   List of {"role": ..., "content": ...} dicts
        model:      Model name. Defaults to DEFAULT_LLM_MODEL from config.
        max_tokens: Max output tokens.

    Returns:
        OpenAI-compatible response dict

    Raises:
        RuntimeError: Both LiteLLM and Ollama are unreachable
    """
    model = model or config.DEFAULT_LLM_MODEL

    # LiteLLM proxy uses model IDs without colons (e.g. "llama3.1-8b").
    # Ollama native API uses colons (e.g. "llama3.1:8b").
    # Map: strip provider prefix if present, then convert ":" to "-" for LiteLLM.
    base_model = model.split("/")[-1] if "/" in model else model
    litellm_model = base_model.replace(":", "-")

    payload = {
        "model":      litellm_model,
        "messages":   messages,
        "max_tokens": max_tokens,
        "stream":     False,
    }

    # Try LiteLLM proxy first
    try:
        async with httpx.AsyncClient(base_url=config.LITELLM_URL, timeout=60.0) as client:
            resp = await client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            return resp.json()
    except (httpx.ConnectError, httpx.TimeoutException):
        pass  # fall through to Ollama
    except httpx.HTTPStatusError as e:
        if e.response.status_code not in (502, 503, 504):
            raise RuntimeError(f"LiteLLM error {e.response.status_code}: {e.response.text[:200]}")

    # Fallback: Ollama native API, translate to OpenAI format
    try:
        ollama_payload = {
            "model":    model,
            "messages": messages,
            "stream":   False,
            "options":  {"num_predict": max_tokens},
        }
        async with httpx.AsyncClient(base_url=config.OLLAMA_URL, timeout=60.0) as client:
            resp = await client.post("/api/chat", json=ollama_payload)
            resp.raise_for_status()
            data = resp.json()

        # Translate Ollama response → OpenAI format
        return {
            "id":      "ollama-" + data.get("created_at", ""),
            "object":  "chat.completion",
            "model":   model,
            "choices": [{
                "index":         0,
                "message":       data.get("message", {"role": "assistant", "content": ""}),
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens":     data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens":      data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        }
    except httpx.ConnectError:
        raise RuntimeError(
            f"Neither LiteLLM ({config.LITELLM_URL}) nor Ollama ({config.OLLAMA_URL}) is reachable"
        )
    except httpx.HTTPStatusError as e:
        raise RuntimeError(f"Ollama error {e.response.status_code}: {e.response.text[:200]}")
