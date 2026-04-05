"""
Web scraping and structured data extraction.

Fetches a URL, parses HTML with BeautifulSoup, extracts:
  - Requested fields (text, links, meta, headings, tables, etc.)
  - Full text and title by default

Returns: dict with extracted data
"""
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; x402-MCP-Scraper/1.0; +https://x402.org)"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_ALLOWED_FIELDS = {
    "title", "text", "links", "meta", "headings",
    "tables", "images", "og_tags", "structured_data",
}


async def scrape(url: str, extract_fields: list[str] | None = None) -> dict[str, Any]:
    """
    Fetch and extract structured data from a URL.

    Args:
        url:            Target URL (must be http/https)
        extract_fields: Which fields to return. Defaults to ["title", "text", "meta"].
                        Allowed: title, text, links, meta, headings, tables,
                                 images, og_tags, structured_data

    Returns:
        Dict of extracted data plus metadata (url, status_code, content_type)

    Raises:
        ValueError: Invalid URL scheme
        RuntimeError: Fetch failed
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are supported, got: {parsed.scheme}")

    fields = set(extract_fields or ["title", "text", "meta"])
    unknown = fields - _ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"Unknown extract_fields: {unknown}. Allowed: {_ALLOWED_FIELDS}")

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
        raise RuntimeError(f"Request to {url} timed out")

    content_type = resp.headers.get("content-type", "")
    result: dict[str, Any] = {
        "url":          str(resp.url),
        "status_code":  resp.status_code,
        "content_type": content_type,
    }

    if "text/html" not in content_type and "application/xhtml" not in content_type:
        result["warning"] = f"Non-HTML content type: {content_type}"
        result["raw_text"] = resp.text[:2000]
        return result

    soup = BeautifulSoup(resp.text, "html.parser")

    # Always include title
    title_tag = soup.find("title")
    result["title"] = title_tag.get_text(strip=True) if title_tag else ""

    if "text" in fields:
        # Clean body text: strip scripts, styles, nav, footer
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        result["text"] = " ".join(soup.get_text(" ", strip=True).split())[:10000]

    if "links" in fields:
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                abs_href = urljoin(url, href)
                links.append({"text": a.get_text(strip=True)[:120], "href": abs_href})
        result["links"] = links[:100]

    if "meta" in fields:
        meta = {}
        for tag in soup.find_all("meta"):
            name = tag.get("name") or tag.get("property") or tag.get("http-equiv")
            content = tag.get("content")
            if name and content:
                meta[name.lower()] = content
        result["meta"] = meta

    if "headings" in fields:
        headings = []
        for level in range(1, 7):
            for h in soup.find_all(f"h{level}"):
                headings.append({"level": level, "text": h.get_text(strip=True)})
        result["headings"] = headings

    if "images" in fields:
        images = []
        for img in soup.find_all("img", src=True):
            images.append({
                "src": urljoin(url, img["src"]),
                "alt": img.get("alt", ""),
            })
        result["images"] = images[:50]

    if "og_tags" in fields:
        og = {}
        for tag in soup.find_all("meta", property=re.compile(r"^og:")):
            og[tag["property"]] = tag.get("content", "")
        result["og_tags"] = og

    if "tables" in fields:
        tables = []
        for tbl in soup.find_all("table"):
            rows = []
            for tr in tbl.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)
            if rows:
                tables.append(rows)
        result["tables"] = tables[:10]

    if "structured_data" in fields:
        scripts = soup.find_all("script", type="application/ld+json")
        import json as _json
        structured = []
        for s in scripts:
            try:
                structured.append(_json.loads(s.string or "{}"))
            except Exception:
                pass
        result["structured_data"] = structured

    return result
