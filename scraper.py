"""Scrapes a company website to extract mission, vision, and about info."""
import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; JDGenerator/1.0)"
}
MAX_CHARS = 3000  # limit context sent to Claude


def _normalize_url(url: str) -> str:
    """Ensure URL has https:// and strip www. for consistency."""
    if not url:
        return url
    if not url.startswith("http"):
        url = "https://" + url
    # Strip www. so torqmtb.com and www.torqmtb.com both resolve the same way
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return parsed._replace(netloc=host).geturl()


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
    url = _normalize_url(url)
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
                    if img_res.status_code == 200 and len(img_res.content) > 100:
                        return img_res.content
                except Exception:
                    continue
        except Exception:
            return None
    return None


def _luminance(hex_color: str) -> float:
    """Return relative luminance (0=black, 1=white) for a hex color like #RRGGBB."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    def linearize(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def _pick_color(css_text: str) -> str | None:
    """Pick the most-used saturated hex color from a CSS string. Returns None if nothing useful."""
    from collections import Counter
    BRAND_PROPS = [
        "--color-primary", "--primary", "--brand", "--brand-primary",
        "--accent", "--main-color", "--primary-color", "--theme-color",
        "--main", "--color-brand", "--color-accent", "--color-secondary",
        "--secondary", "--highlight",
    ]
    # Check CSS custom properties first
    for prop in BRAND_PROPS:
        match = re.search(re.escape(prop) + r"\s*:\s*(#[0-9a-fA-F]{6})", css_text)
        if match:
            return match.group(1)
    # Fall back to most-used saturated color
    candidates = []
    for h in re.findall(r"#([0-9a-fA-F]{6})\b", css_text):
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
        max_c, min_c = max(r, g, b), min(r, g, b)
        saturation = (max_c - min_c) / max_c if max_c else 0
        lightness = (max_c + min_c) / 510
        if saturation > 0.2 and saturation < 0.95 and 0.1 < lightness < 0.85:
            candidates.append("#" + h)
    if candidates:
        return Counter(candidates).most_common(1)[0][0]
    return None


async def extract_brand_colors(url: str) -> dict:
    """
    Extract primary brand color from a company website.
    Returns {"primary": "#RRGGBB", "text_on_primary": "white" | "dark"}.
    Falls back to defaults (teal) if nothing found.
    """
    DEFAULT = {"primary": "#0A4444", "text_on_primary": "white"}
    if not url:
        return DEFAULT
    url = _normalize_url(url)
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
        try:
            res = await client.get(url)
            if res.status_code != 200:
                return DEFAULT
        except Exception:
            return DEFAULT

        soup = BeautifulSoup(res.text, "html.parser")

        # 1. <meta name="theme-color">
        meta = soup.find("meta", attrs={"name": "theme-color"})
        if meta and meta.get("content", "").startswith("#"):
            color = meta["content"][:7]
            lum = _luminance(color)
            return {"primary": color, "text_on_primary": "white" if lum < 0.4 else "dark"}

        # 2. Inline <style> tags
        inline_css = " ".join(tag.string or "" for tag in soup.find_all("style"))
        color = _pick_color(inline_css)
        if color:
            lum = _luminance(color)
            return {"primary": color, "text_on_primary": "white" if lum < 0.4 else "dark"}

        # 3. External stylesheets (up to 2, cap at 50KB each)
        ext_css = ""
        sheet_links = [
            urljoin(base, tag["href"])
            for tag in soup.find_all("link", rel=lambda r: r and "stylesheet" in r)
            if tag.get("href")
        ][:2]
        for sheet_url in sheet_links:
            try:
                sheet_res = await client.get(sheet_url)
                if sheet_res.status_code == 200:
                    ext_css += sheet_res.text[:50000]
            except Exception:
                continue
        if ext_css:
            color = _pick_color(ext_css)
            if color:
                lum = _luminance(color)
                return {"primary": color, "text_on_primary": "white" if lum < 0.4 else "dark"}

    return DEFAULT


async def scrape_company(url: str) -> str:
    """Fetch homepage and /about page, return combined plain text (capped at MAX_CHARS)."""
    if not url:
        return ""
    url = _normalize_url(url)

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
