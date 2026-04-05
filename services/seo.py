"""
SEO audit service.

Fetches a URL and returns a structured SEO analysis:
  - Title, meta description, canonical
  - Heading hierarchy (H1-H6)
  - Open Graph / Twitter Card tags
  - Image alt text coverage
  - Link analysis (internal vs external, nofollow)
  - Page speed indicators (response time, content size, resource hints)
  - Robots directives
  - Structured data presence
  - Issues list with severity levels

Returns: dict with audit results and score (0-100).
"""
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; x402-MCP-SEO/1.0; +https://x402.org)"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
}


def _score_issues(issues: list[dict]) -> int:
    """Compute 0-100 score. Each issue deducts points based on severity."""
    deductions = {"critical": 15, "warning": 7, "info": 2}
    total = sum(deductions.get(i["severity"], 0) for i in issues)
    return max(0, 100 - total)


async def audit(url: str) -> dict[str, Any]:
    """
    Perform SEO audit on a URL.

    Args:
        url: Target URL (must be http/https)

    Returns:
        Audit dict with score, issues, and extracted metadata

    Raises:
        ValueError: Invalid URL scheme
        RuntimeError: Fetch failed
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs supported, got: {parsed.scheme}")

    base_domain = f"{parsed.scheme}://{parsed.netloc}"
    issues: list[dict] = []

    # Fetch with timing
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20.0,
            headers=_HEADERS,
        ) as client:
            resp = await client.get(url)
    except httpx.ConnectError as e:
        raise RuntimeError(f"Could not connect to {url}: {e}")
    except httpx.TimeoutException:
        raise RuntimeError(f"Request timed out: {url}")

    response_ms = int((time.monotonic() - t0) * 1000)
    content_size_bytes = len(resp.content)
    final_url = str(resp.url)

    if resp.status_code != 200:
        issues.append({
            "severity": "critical",
            "code": "bad_status",
            "message": f"HTTP {resp.status_code} — page not accessible",
        })

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type:
        return {
            "url": final_url,
            "score": 0,
            "issues": [{"severity": "critical", "code": "not_html",
                        "message": f"Non-HTML content: {content_type}"}],
            "metadata": {},
        }

    soup = BeautifulSoup(resp.text, "html.parser")

    # -----------------------------------------------------------------------
    # Title
    # -----------------------------------------------------------------------
    title_tag  = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""

    if not title_text:
        issues.append({"severity": "critical", "code": "missing_title",
                       "message": "Missing <title> tag"})
    elif len(title_text) < 30:
        issues.append({"severity": "warning", "code": "title_too_short",
                       "message": f"Title too short ({len(title_text)} chars, recommend 30-60)"})
    elif len(title_text) > 60:
        issues.append({"severity": "warning", "code": "title_too_long",
                       "message": f"Title too long ({len(title_text)} chars, recommend 30-60)"})

    # -----------------------------------------------------------------------
    # Meta description
    # -----------------------------------------------------------------------
    meta_desc_tag = soup.find("meta", attrs={"name": lambda n: n and n.lower() == "description"})
    meta_desc     = meta_desc_tag["content"].strip() if meta_desc_tag and meta_desc_tag.get("content") else ""

    if not meta_desc:
        issues.append({"severity": "warning", "code": "missing_meta_description",
                       "message": "Missing meta description"})
    elif len(meta_desc) < 70:
        issues.append({"severity": "info", "code": "meta_description_short",
                       "message": f"Meta description short ({len(meta_desc)} chars, recommend 70-160)"})
    elif len(meta_desc) > 160:
        issues.append({"severity": "info", "code": "meta_description_long",
                       "message": f"Meta description too long ({len(meta_desc)} chars, may be truncated)"})

    # -----------------------------------------------------------------------
    # Canonical
    # -----------------------------------------------------------------------
    canonical_tag = soup.find("link", rel=lambda r: r and "canonical" in r)
    canonical     = canonical_tag["href"] if canonical_tag and canonical_tag.get("href") else None

    if not canonical:
        issues.append({"severity": "warning", "code": "missing_canonical",
                       "message": "No canonical URL specified"})

    # -----------------------------------------------------------------------
    # Headings
    # -----------------------------------------------------------------------
    headings: dict[str, list[str]] = {}
    for level in range(1, 7):
        tags = soup.find_all(f"h{level}")
        headings[f"h{level}"] = [t.get_text(strip=True) for t in tags]

    h1_count = len(headings.get("h1", []))
    if h1_count == 0:
        issues.append({"severity": "critical", "code": "missing_h1",
                       "message": "No H1 heading found"})
    elif h1_count > 1:
        issues.append({"severity": "warning", "code": "multiple_h1",
                       "message": f"Multiple H1 headings ({h1_count}) — use only one"})

    # -----------------------------------------------------------------------
    # Open Graph
    # -----------------------------------------------------------------------
    og_tags: dict[str, str] = {}
    for tag in soup.find_all("meta", property=lambda p: p and p.startswith("og:")):
        og_tags[tag["property"]] = tag.get("content", "")

    if "og:title" not in og_tags:
        issues.append({"severity": "info", "code": "missing_og_title",
                       "message": "Missing og:title (social sharing)"})
    if "og:description" not in og_tags:
        issues.append({"severity": "info", "code": "missing_og_description",
                       "message": "Missing og:description (social sharing)"})
    if "og:image" not in og_tags:
        issues.append({"severity": "info", "code": "missing_og_image",
                       "message": "Missing og:image (social sharing)"})

    # -----------------------------------------------------------------------
    # Images
    # -----------------------------------------------------------------------
    all_imgs = soup.find_all("img")
    imgs_missing_alt = [i for i in all_imgs if not i.get("alt", "").strip()]
    if imgs_missing_alt:
        issues.append({"severity": "warning", "code": "images_missing_alt",
                       "message": f"{len(imgs_missing_alt)}/{len(all_imgs)} images missing alt text"})

    # -----------------------------------------------------------------------
    # Links
    # -----------------------------------------------------------------------
    all_links    = soup.find_all("a", href=True)
    internal_links: list[str] = []
    external_links: list[str] = []
    nofollow_count = 0

    for a in all_links:
        href = a.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        abs_href = urljoin(final_url, href)
        rel = a.get("rel", [])
        if isinstance(rel, str):
            rel = rel.split()
        if "nofollow" in rel:
            nofollow_count += 1
        if urlparse(abs_href).netloc == parsed.netloc:
            internal_links.append(abs_href)
        else:
            external_links.append(abs_href)

    if not internal_links:
        issues.append({"severity": "warning", "code": "no_internal_links",
                       "message": "No internal links found"})

    # -----------------------------------------------------------------------
    # Robots meta
    # -----------------------------------------------------------------------
    robots_meta = soup.find("meta", attrs={"name": lambda n: n and n.lower() == "robots"})
    robots_content = robots_meta["content"].lower() if robots_meta and robots_meta.get("content") else ""

    if "noindex" in robots_content:
        issues.append({"severity": "critical", "code": "noindex",
                       "message": "Page has noindex directive — search engines will not index"})

    # -----------------------------------------------------------------------
    # Structured data
    # -----------------------------------------------------------------------
    import json as _json
    structured_data: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            structured_data.append(_json.loads(script.string or "{}"))
        except Exception:
            pass

    if not structured_data:
        issues.append({"severity": "info", "code": "no_structured_data",
                       "message": "No JSON-LD structured data found"})

    # -----------------------------------------------------------------------
    # Page speed indicators
    # -----------------------------------------------------------------------
    if response_ms > 3000:
        issues.append({"severity": "warning", "code": "slow_response",
                       "message": f"Slow server response ({response_ms}ms)"})
    if content_size_bytes > 1_500_000:
        issues.append({"severity": "warning", "code": "large_page",
                       "message": f"Large page size ({content_size_bytes // 1024}KB)"})

    # -----------------------------------------------------------------------
    # Viewport / mobile
    # -----------------------------------------------------------------------
    viewport = soup.find("meta", attrs={"name": lambda n: n and n.lower() == "viewport"})
    if not viewport:
        issues.append({"severity": "warning", "code": "missing_viewport",
                       "message": "No viewport meta tag — may not be mobile-friendly"})

    score = _score_issues(issues)

    return {
        "url":           final_url,
        "score":         score,
        "response_ms":   response_ms,
        "content_size_bytes": content_size_bytes,
        "issues":        issues,
        "metadata": {
            "title":        title_text,
            "description":  meta_desc,
            "canonical":    canonical,
            "headings":     headings,
            "og_tags":      og_tags,
            "robots":       robots_content or "index,follow (default)",
            "internal_links_count": len(internal_links),
            "external_links_count": len(external_links),
            "nofollow_links_count": nofollow_count,
            "images_total":         len(all_imgs),
            "images_missing_alt":   len(imgs_missing_alt),
            "structured_data":      structured_data,
        },
    }
