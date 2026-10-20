"""Save a web page as plain text so it can be read offline later (standard library only)."""
import re
import urllib.request
from html.parser import HTMLParser

import config


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip, self.parts, self.title, self._in_title = 0, [], "", False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header", "noscript"):
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header", "noscript") and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def save_page(url):
    """Download a page and store it in library/saved_pages. Returns a friendly message."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "Paste a full link that starts with http:// or https://"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OfflineScholar/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read(3_000_000).decode("utf-8", errors="ignore")
    except Exception:
        return "No internet connection (or the page could not be opened). Try again when you are online."
    p = _Text()
    p.feed(html)
    text = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", "".join(p.parts))).strip()
    if len(text.split()) < 30:
        return "That page had almost no readable text, so it was not saved."
    title = (p.title or url).strip()
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "page"
    config.SAVED_DIR.mkdir(parents=True, exist_ok=True)
    (config.SAVED_DIR / f"{slug}.txt").write_text(f"{title}\n{url}\n\n{text}", encoding="utf-8")
    return f"Saved: {title}. Now press Re-scan library."
