"""Save a web page as plain text so it can be read offline later (standard library only)."""
import hashlib
import re
import urllib.request
from html.parser import HTMLParser

import config

BLOCK_TAGS = {"p", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th",
              "pre", "blockquote", "div", "section", "article", "table", "ul", "ol"}
SKIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript", "svg", "form", "aside"}


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip, self.parts, self.title, self._in_title = 0, [], "", False

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip += 1
        if tag == "title":
            self._in_title = True
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip:
            self.skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self.skip:
            self.parts.append(data)


def _slug(title, url):
    """Readable file name that stays unique per URL, so pages with the same title do not overwrite."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50] or "page"
    return f"{slug}-{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def save_page(url):
    """Download a page and store it in library/saved_pages. Returns a friendly message."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return "Paste a full link that starts with http:// or https://"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OfflineScholar/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            ctype = (r.headers.get_content_type() or "").lower()
            if ctype and not (ctype.startswith("text/") or "html" in ctype):
                return f"That link is not a web page ({ctype})."
            charset = r.headers.get_content_charset() or "utf-8"
            html = r.read(3_000_000).decode(charset, errors="ignore")
    except Exception:
        return "No internet connection (or the page could not be opened). Try again when you are online."
    p = _Text()
    p.feed(html)
    text = re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", "".join(p.parts))).strip()
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    if len(text.split()) < 30:
        return "That page had almost no readable text, so it was not saved."
    title = (p.title or "").strip() or url
    config.SAVED_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.SAVED_DIR / f"{_slug(title, url)}.txt"
    try:
        dest.write_text(f"{title}\n{url}\n\n{text}", encoding="utf-8")
    except OSError as e:
        return f"Could not save the page: {e}"
    return f"Saved: {title}. Now press Re-scan library."
