"""Optional live web lookup for current questions.

Uses Brave's public search page, then DuckDuckGo and Wikipedia as fallbacks, so
it needs no API key. It is only called when the user turns on the "Live lookup"
switch; normal offline answers never touch it.
"""
import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

TIMEOUT = 15
MAX_RESULTS = 5


class _Results(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self._field = None
        self._parts = []
        self._href = ""

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attributes = dict(attrs)
        classes = attributes.get("class", "")
        if "result__a" in classes:
            self._field = "title"
            self._href = attributes.get("href", "")
            self._parts = []
        elif "result__snippet" in classes and self.results:
            self._field = "snippet"
            self._parts = []

    def handle_data(self, data):
        if self._field:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag != "a" or not self._field:
            return
        text = re.sub(r"\s+", " ", " ".join(self._parts)).strip()
        if self._field == "title" and text:
            self.results.append({"title": text, "url": _real_url(self._href), "snippet": ""})
        elif self._field == "snippet" and self.results:
            self.results[-1]["snippet"] = text
        self._field = None
        self._parts = []


def _real_url(href):
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        redirected = urllib.parse.parse_qs(parsed.query).get("uddg")
        if redirected:
            return redirected[0]
    return href


def _host(url):
    try:
        return urllib.parse.urlparse(url).netloc.removeprefix("www.")
    except ValueError:
        return url


def _clean(value):
    text = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(
        r"^(?:\d+\s+(?:minute|hour|day|week|month|year)s?\s+ago"
        r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4})"
        r"\s*[-\u2013]\s*", "", text, flags=re.I)
    return text


def _brave(question, limit):
    url = ("https://search.brave.com/search?q=" + urllib.parse.quote_plus(question)
           + "&source=web")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            page = response.read(3_000_000).decode("utf-8", errors="ignore")
    except Exception:
        return []
    return _enrich_wikipedia(_parse_brave(page, limit, url))


def _enrich_wikipedia(passages):
    """Use a full Wikipedia intro for person entities, not just their snippet."""
    if not passages:
        return passages
    if passages[0].get("entity"):
        title = passages[0]["label"].removeprefix("Brave entity: ")
        intro = _wiki_intro(title)
        if intro:
            passages = [item for item in passages if item.get("url") != intro["url"]]
            passages.insert(1, intro)
        return passages
    first = passages[0]
    label = first.get("label", "")
    if first.get("name") == "en.wikipedia.org" and not label.lower().startswith("list of"):
        title = label.split(" - ")[0]
        intro = _wiki_intro(title)
        if intro:
            first["text"] = intro["text"]
            first["provider"] = "Wikipedia"
    return passages


def _parse_brave(page, limit, url="https://search.brave.com/"):
    passages = []
    entity = re.search(
        r'entity-infobox-header-title-row[^>]*>.*?<div[^>]*>(.*?)</div>', page, re.S)
    if entity:
        title = _clean(entity.group(1))
        description = ""
        marker = page.find("entity-infobox-description", entity.end())
        if marker > 0:
            found = re.search(r">(.*?)</div>", page[marker:], re.S)
            if found:
                description = _clean(found.group(1))
        if title:
            passages.append({
                "path": url, "url": url, "name": "search.brave.com",
                "label": "Brave entity: " + title,
                "text": title + (" - " + description if description else ""),
                "score": 1.0, "provider": "Brave", "entity": True,
            })

    seen = set()
    for block in re.split(r'<div class="result-wrapper[^"]*"', page)[1:]:
        href = re.search(r'href="(https?://[^"]+)"[^>]*class="[^"]*\bl1\b[^"]*"', block)
        title = re.search(r'class="title search-snippet-title[^"]*"[^>]*>(.*?)</div>',
                          block, re.S)
        snippet = re.search(r'<div class="content[^"]*"[^>]*>(.*?)</div>', block, re.S)
        if not href or not title:
            continue
        link = html.unescape(href.group(1))
        if link in seen or not link.startswith("http"):
            continue
        seen.add(link)
        name = _host(link)
        heading = _clean(title.group(1))
        text = _clean(snippet.group(1)) if snippet else ""
        if not text:
            continue
        passages.append({
            "path": link, "url": link, "name": name, "label": heading,
            "text": text, "score": 1.0, "provider": "Brave",
        })
        if len(passages) >= limit + 1:
            break
    return passages


def _duckduckgo(question, limit):
    query = urllib.parse.quote_plus(question)
    request = urllib.request.Request(
        "https://html.duckduckgo.com/html/?q=" + query,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            html = response.read(2_000_000).decode("utf-8", errors="ignore")
    except Exception:
        return []
    parser = _Results()
    try:
        parser.feed(html)
    except Exception:
        return []

    passages, seen = [], set()
    for item in parser.results:
        url, snippet = item["url"], item["snippet"]
        if not snippet or not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        passages.append({
            "path": url,
            "url": url,
            "name": _host(url),
            "label": item["title"],
            "text": snippet,
            "score": 1.0,
            "provider": "DuckDuckGo",
        })
        if len(passages) >= limit:
            break
    return passages


def _wiki_intro(title):
    """Fetch a Wikipedia intro for an entity found in the search results."""
    api = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "prop": "extracts", "explaintext": 1, "exintro": 1,
        "redirects": 1, "titles": title, "format": "json",
    })
    try:
        with urllib.request.urlopen(
                urllib.request.Request(api, headers={
                    "User-Agent": "OfflineScholar/1.0 (local study assistant)"}),
                timeout=TIMEOUT) as response:
            pages = json.loads(response.read().decode("utf-8", errors="ignore"))
        page = next(iter(pages["query"]["pages"].values()))
        text = (page.get("extract") or "").strip()
        name = page.get("title", title)
    except Exception:
        return None
    if len(text.split()) < 10:
        return None
    url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(name.replace(" ", "_"))
    return {
        "path": url, "url": url, "name": "en.wikipedia.org",
        "label": name + " - Wikipedia", "text": text,
        "score": 1.0, "provider": "Wikipedia",
    }


def _wikipedia(question, limit=3):
    """Fallback for entities and officeholders; uses the public MediaWiki API."""
    user_agent = {"User-Agent": "OfflineScholar/1.0 (local study assistant)"}
    search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "list": "search", "srsearch": question,
        "format": "json", "srlimit": limit,
    })
    try:
        with urllib.request.urlopen(urllib.request.Request(search_url, headers=user_agent),
                                    timeout=TIMEOUT) as response:
            found = json.loads(response.read().decode("utf-8", errors="ignore"))
        titles = [item["title"] for item in found["query"]["search"]]
    except Exception:
        return []
    if not titles:
        return []
    extract_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "prop": "extracts", "explaintext": 1, "exintro": 1,
        "redirects": 1, "exlimit": "max", "titles": "|".join(titles), "format": "json",
    })
    try:
        with urllib.request.urlopen(urllib.request.Request(extract_url, headers=user_agent),
                                    timeout=TIMEOUT) as response:
            pages = json.loads(response.read().decode("utf-8", errors="ignore"))
    except Exception:
        return []
    passages = []
    for page in pages.get("query", {}).get("pages", {}).values():
        title, text = page.get("title", ""), (page.get("extract") or "").strip()
        if not title or len(text.split()) < 10:
            continue
        url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        passages.append({
            "path": url,
            "url": url,
            "name": "en.wikipedia.org",
            "label": title,
            "text": text[:1200],
            "score": 0.8,
            "provider": "Wikipedia",
        })
    return passages


def search(question, limit=MAX_RESULTS):
    """Return (passages, error). Passages are snippets with source URLs."""
    question = (question or "").strip()
    if not question:
        return [], "Ask a question first."
    passages = _brave(question, limit)
    if not passages:
        passages = _duckduckgo(question, limit)
    if not passages:
        passages = _wikipedia(question)
    if not passages:
        return [], "I could not reach a web search service or find a usable result. Try again."
    return passages, None
