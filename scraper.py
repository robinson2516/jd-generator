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

            # Priority order: og:image → apple-touch-icon → logo img → favicon
            candidates = []
            og = soup.find("meta", property="og:image")
            if og and og.get("content"):
                candidates.append(og["content"])
            apple = soup.find("link", rel=lambda r: r and "apple-touch-icon" in r)
            if apple and apple.get("href"):
                candidates.append(urljoin(base, apple["href"]))
            # <img> tags with "logo" in id, class, src, or alt
            for img in soup.find_all("img"):
                attrs = " ".join([
                    img.get("id", ""), img.get("alt", ""),
                    " ".join(img.get("class") or []), img.get("src", ""),
                ]).lower()
                if "logo" in attrs and img.get("src"):
                    candidates.append(urljoin(base, img["src"]))
                    break
            icon = soup.find("link", rel=lambda r: r and "icon" in r)
            if icon and icon.get("href"):
                candidates.append(urljoin(base, icon["href"]))
            candidates.append(urljoin(base, "/favicon.ico"))

            for img_url in candidates:
                try:
                    img_res = await client.get(img_url)
                    if img_res.status_code == 200 and len(img_res.content) > 100:
                        # Skip SVGs — reportlab/Pillow can't render them
                        content = img_res.content
                        is_svg = content[:200].lstrip().startswith(b"<") and b"svg" in content[:200].lower()
                        if not is_svg:
                            return content
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


def _pick_bg_color(css_text: str) -> str | None:
    """Find background-color used on nav/header/button selectors — likely a brand color."""
    pattern = re.compile(
        r'(?:nav|header|\.header|\.nav|\.navbar|\.btn|button|\.site-header|\.top-bar)'
        r'[^{]{0,120}\{[^}]{0,400}background(?:-color)?\s*:\s*(#[0-9a-fA-F]{6})',
        re.IGNORECASE | re.DOTALL,
    )
    colors = []
    for match in pattern.finditer(css_text):
        c = match.group(1)
        r = int(c[1:3], 16); g = int(c[3:5], 16); b = int(c[5:7], 16)
        # Skip near-white and near-black
        if 20 < r + g + b < 700:
            colors.append(c)
    if colors:
        from collections import Counter
        return Counter(colors).most_common(1)[0][0]
    return None


def _pick_color(css_text: str) -> str | None:
    """Find a brand color via CSS custom properties only. Returns None if nothing found."""
    BRAND_PROPS = [
        "--color-primary", "--primary", "--brand", "--brand-primary",
        "--accent", "--main-color", "--primary-color", "--theme-color",
        "--main", "--color-brand", "--color-accent", "--color-secondary",
        "--secondary", "--highlight", "--btn-bg", "--button-bg",
        "--nav-bg", "--header-bg", "--header-background",
    ]
    for prop in BRAND_PROPS:
        match = re.search(re.escape(prop) + r"\s*:\s*(#[0-9a-fA-F]{6})", css_text)
        if match:
            return match.group(1)
    return None


def _is_usable_brand_color(hex_color: str) -> bool:
    """Return True if color is suitable as a PDF header background (not too dark/light/grey)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    lum = _luminance(hex_color)
    max_c, min_c = max(r, g, b), min(r, g, b)
    saturation = (max_c - min_c) / max_c if max_c else 0
    # Must have some color (not grey) and not be near-black or near-white
    return saturation > 0.15 and 0.04 < lum < 0.75


async def extract_brand_colors(url: str) -> dict:
    """
    Extract primary brand color from a company website using Claude AI.
    Falls back to CSS parsing, then defaults if needed.
    Returns {"primary": "#RRGGBB", "text_on_primary": "white" | "dark"}.
    """
    DEFAULT = {"primary": "#0A4444", "text_on_primary": "white"}
    if not url:
        return DEFAULT
    url = _normalize_url(url)
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"

    all_css = ""
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            res = await client.get(url)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")

                # 1. <meta name="theme-color">
                meta = soup.find("meta", attrs={"name": "theme-color"})
                if meta and meta.get("content", "").startswith("#"):
                    color = meta["content"][:7]
                    if _is_usable_brand_color(color):
                        lum = _luminance(color)
                        return {"primary": color, "text_on_primary": "white" if lum < 0.4 else "dark"}

                # 2. Inline + same-domain external CSS
                SKIP_KEYWORDS = ("bootstrap", "fontawesome", "font-awesome", "foundation",
                                 "bulma", "tailwind", "animate", "jquery", "normalize", "reset")
                inline_css = " ".join(tag.string or "" for tag in soup.find_all("style"))
                all_sheets = [
                    urljoin(base, tag["href"])
                    for tag in soup.find_all("link", rel=lambda r: r and "stylesheet" in r)
                    if tag.get("href")
                ]
                same_domain = [s for s in all_sheets
                               if urlparse(s).netloc == urlparse(base).netloc
                               and not any(k in s.lower() for k in SKIP_KEYWORDS)]
                ext_css = ""
                for sheet_url in same_domain[:3]:
                    try:
                        sheet_res = await client.get(sheet_url)
                        if sheet_res.status_code == 200:
                            ext_css += sheet_res.text[:80000]
                    except Exception:
                        continue

                all_css = inline_css + " " + ext_css

                # 3. CSS custom properties
                color = _pick_color(all_css)
                if color and _is_usable_brand_color(color):
                    lum = _luminance(color)
                    return {"primary": color, "text_on_primary": "white" if lum < 0.4 else "dark"}

                # 4. Background color on nav/header/button selectors
                color = _pick_bg_color(all_css)
                if color and _is_usable_brand_color(color):
                    lum = _luminance(color)
                    return {"primary": color, "text_on_primary": "white" if lum < 0.4 else "dark"}
    except Exception:
        pass

    # 5. Claude fallback — always runs, even if site is blocked/unreachable
    try:
        import anthropic, os
        client_ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        context = f"CSS:\n{all_css[:3000]}" if all_css.strip() else ""
        msg = client_ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=20,
            messages=[{
                "role": "user",
                "content": (
                    f"What is the primary brand hex color for the company at {base}? "
                    f"Reply with ONLY the hex color (e.g. #F96302). No explanation. {context}"
                ),
            }],
        )
        color = re.search(r"#[0-9a-fA-F]{6}", msg.content[0].text)
        if color:
            c = color.group(0)
            if _is_usable_brand_color(c):
                lum = _luminance(c)
                return {"primary": c, "text_on_primary": "white" if lum < 0.4 else "dark"}
    except Exception:
        pass

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
