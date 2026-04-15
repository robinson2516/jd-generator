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


async def fetch_logo(url: str) -> bytes | None:
    """Try to fetch the company logo from og:image, apple-touch-icon, or favicon."""
    if not url:
        return None
    if not url.startswith("http"):
        url = "https://" + url
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
        try:
            res = await client.get(url)
            if res.status_code != 200:
                return None
            soup = BeautifulSoup(res.text, "html.parser")

            # Priority order: og:image → apple-touch-icon → favicon
            candidates = []
            og = soup.find("meta", property="og:image")
            if og and og.get("content"):
                candidates.append(og["content"])
            apple = soup.find("link", rel=lambda r: r and "apple-touch-icon" in r)
            if apple and apple.get("href"):
                candidates.append(urljoin(base, apple["href"]))
            icon = soup.find("link", rel=lambda r: r and "icon" in r)
            if icon and icon.get("href"):
                candidates.append(urljoin(base, icon["href"]))
            candidates.append(urljoin(base, "/favicon.ico"))

            for img_url in candidates:
                try:
                    img_res = await client.get(img_url)
                    if img_res.status_code == 200 and len(img_res.content) > 500:
                        return img_res.content
                except Exception:
                    continue
        except Exception:
            return None
    return None


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
