"""Scrapes a company website to extract mission, vision, and about info."""
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JDGenerator/1.0)"
}
MAX_CHARS = 3000  # limit context sent to Claude


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "img"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


async def scrape_company(url: str) -> str:
    """Fetch homepage and /about page, return combined plain text (capped at MAX_CHARS)."""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url

    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    pages = [url, urljoin(base, "/about"), urljoin(base, "/about-us")]

    collected = []
    async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
        for page_url in pages:
            try:
                res = await client.get(page_url)
                if res.status_code == 200:
                    text = _extract_text(res.text)
                    if text:
                        collected.append(text)
            except Exception:
                continue

    combined = " ".join(collected)
    return combined[:MAX_CHARS].strip()
