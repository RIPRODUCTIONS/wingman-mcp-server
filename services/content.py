"""
Content generation via local LLM (Ollama/LiteLLM).

Supports: blog_post, social_caption, script, email, product_description.
Returns: dict with generated text and metadata.
"""
from typing import Any

from . import llm as llm_service
from .. import config

# Content type → system prompt + length guidance
_TYPE_CONFIG: dict[str, dict] = {
    "blog_post": {
        "system": (
            "You are an expert content writer. Write in a clear, engaging, SEO-friendly style. "
            "Use proper headings (H2, H3 with ##, ###), bullet points, and varied sentence length. "
            "Do not add a title — start directly with the intro paragraph."
        ),
        "max_tokens_default": 1200,
    },
    "social_caption": {
        "system": (
            "You are a social media expert. Write punchy, engaging captions optimized for engagement. "
            "Include relevant hashtags at the end. Keep it concise and conversational. "
            "No quotation marks around the caption — output only the caption text."
        ),
        "max_tokens_default": 200,
    },
    "script": {
        "system": (
            "You are a professional scriptwriter. Write clear, natural-sounding dialogue and narration "
            "for video content. Format as: [NARRATOR] or [HOST]: text on separate lines. "
            "Include scene direction in [brackets] sparingly."
        ),
        "max_tokens_default": 800,
    },
    "email": {
        "system": (
            "You are an email copywriter. Write professional, persuasive emails with a clear subject line "
            "(prefix with 'Subject: '), greeting, body, and sign-off. "
            "Match tone to context — marketing, transactional, or outreach."
        ),
        "max_tokens_default": 500,
    },
    "product_description": {
        "system": (
            "You are an e-commerce copywriter. Write compelling product descriptions that highlight "
            "benefits over features. Use sensory language, address customer pain points, "
            "and end with a subtle call to action. No bullet lists unless requested."
        ),
        "max_tokens_default": 300,
    },
}

_VALID_LENGTHS = {"short", "medium", "long"}
_LENGTH_MULTIPLIERS = {"short": 0.5, "medium": 1.0, "long": 2.0}


async def generate(
    content_type: str,
    topic: str,
    length: str = "medium",
    extra_instructions: str = "",
) -> dict[str, Any]:
    """
    Generate content using the local LLM.

    Args:
        content_type:        One of: blog_post, social_caption, script, email, product_description
        topic:               Topic / subject for the content
        length:              short | medium | long
        extra_instructions:  Additional context or style instructions

    Returns:
        {"content_type", "topic", "length", "text", "word_count", "model"}

    Raises:
        ValueError: Unknown content_type or length
        RuntimeError: LLM unavailable
    """
    if content_type not in _TYPE_CONFIG:
        raise ValueError(
            f"Unknown content_type: {content_type!r}. "
            f"Valid types: {sorted(_TYPE_CONFIG.keys())}"
        )
    if length not in _VALID_LENGTHS:
        raise ValueError(f"length must be one of: {_VALID_LENGTHS}")

    cfg = _TYPE_CONFIG[content_type]
    base_tokens = cfg["max_tokens_default"]
    max_tokens = int(base_tokens * _LENGTH_MULTIPLIERS[length])

    user_prompt = f"Topic: {topic}"
    if extra_instructions:
        user_prompt += f"\n\nAdditional instructions: {extra_instructions}"
    if length == "short":
        user_prompt += "\n\nKeep this brief and concise."
    elif length == "long":
        user_prompt += "\n\nBe comprehensive and detailed."

    messages = [
        {"role": "system",  "content": cfg["system"]},
        {"role": "user",    "content": user_prompt},
    ]

    response = await llm_service.chat(
        messages=messages,
        model=config.DEFAULT_LLM_MODEL,
        max_tokens=max_tokens,
    )

    text = response["choices"][0]["message"]["content"].strip()
    model_used = response.get("model", config.DEFAULT_LLM_MODEL)

    return {
        "content_type": content_type,
        "topic":        topic,
        "length":       length,
        "text":         text,
        "word_count":   len(text.split()),
        "model":        model_used,
    }
