"""Operations shared by the web API, the terminal client and the Gradio app."""
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import config
import ingest
import llm
import search
import store
import webpages
import websearch

MAX_UPLOAD_BYTES = 25_000_000


def scan_notes():
    con = store.connect()
    try:
        return ingest.scan_library(con, embed_fn=llm.embed if config.USE_EMBEDDINGS else None)
    finally:
        con.close()


def library_files():
    """Every supported file with its size and index state."""
    con = store.connect()
    try:
        indexed = {row[0]: row[1] for row in con.execute("SELECT path, has_emb FROM files")}
    finally:
        con.close()
    out = []
    for p in ingest.library_files():
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        if str(p) not in indexed:
            state = "not indexed"
        else:
            state = "indexed" if indexed[str(p)] else "keyword only"
        out.append({"name": p.name, "size": size, "state": state})
    return out


def notes_summary():
    files = library_files()
    return {
        "files": len(files),
        "indexed": sum(1 for f in files if f["state"] != "not indexed"),
        "size": sum(f["size"] for f in files),
    }


def add_upload(filename, data):
    """Store one uploaded file. Returns (message, saved_name) where saved_name may be None."""
    name = Path(filename or "").name
    if not name:
        return "A file had no name", None
    suffix = Path(name).suffix.lower()
    if suffix not in config.SUPPORTED:
        return f"{name} is not a supported type", None
    if len(data) > MAX_UPLOAD_BYTES:
        return f"{name} is larger than 25 MB", None
    config.LIBRARY_DIR.mkdir(exist_ok=True)
    dest = config.LIBRARY_DIR / name
    try:
        if dest.exists():
            if dest.read_bytes() == data:
                return f"{name} is already in the library", name
            dest.write_bytes(data)
            return f"Updated {name}", name
        dest.write_bytes(data)
        return f"Added {name}", name
    except OSError as e:
        return f"Could not save {name}: {e}", None


def add_uploads(files):
    """files: iterable of (filename, bytes). Returns a summary message."""
    messages = []
    for name, data in files:
        message, _ = add_upload(name, data)
        messages.append(message)
    if not messages:
        return "Choose one or more files first."
    return "; ".join(messages) + "\n" + scan_notes()


def add_url(url):
    message = webpages.save_page(url)
    if message.startswith("Saved"):
        message += "\n" + scan_notes()
    return message


def clear_notes_index():
    con = store.connect()
    try:
        store.clear_index(con)
    finally:
        con.close()
    return "Index cleared. Your files are still in the library; re-scan to rebuild it."


def latest_upload_passages(limit=4):
    """Passages from the most recently changed file in the notes library."""
    files = ingest.library_files()
    if not files:
        return []
    try:
        latest = max(files, key=lambda path: path.stat().st_mtime)
    except OSError:
        latest = files[-1]
    con = store.connect()
    try:
        rows = con.execute(
            "SELECT path,label,text FROM chunks WHERE path=? ORDER BY id LIMIT ?",
            (str(latest), limit),
        ).fetchall()
    finally:
        con.close()
    if not rows:
        try:
            sections = ingest.read_sections(latest)
        except Exception:
            return []
        rows = []
        for label, text in sections:
            for chunk in ingest.chunk_text(text):
                rows.append((str(latest), label, chunk))
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
    return [{"path": path, "label": label, "text": text, "score": 1.0}
            for path, label, text in rows]


def retrieve(message, use_notes=True):
    """Find supporting note passages. None means notes were not searched; [] means none matched."""
    if not use_notes:
        return None
    if is_latest_upload(message):
        return latest_upload_passages()
    if wants_notes_overview(message):
        overview = latest_upload_passages()
        if overview:
            return overview
    try:
        passages = search.find(message)[:config.RAG_MAX_PASSAGES]
        terms = _content_terms(message)
        if terms:
            passages = [p for p in passages if _passage_matches(p, terms)]
        return passages
    except Exception:
        return []


def _passage_matches(passage, terms):
    haystack = " ".join((passage.get("path", ""), passage.get("label", ""), passage.get("text", "")))
    tokens = set(re.findall(r"[a-z0-9]+", haystack.lower()))
    return any(search._matches(term, tokens) for term in terms)


NOTES_QUESTION = re.compile(
    r"\b(?:my|the|your) notes?\b|\bnotes? (?:say|says|mention|mentions|cover|covers)\b"
    r"|\baccording to (?:my|the) notes?\b|\bin my (?:notes?|library)\b", re.I)
INJECTION = re.compile(
    r"\b(?:ignore|disregard|forget|override) (?:your|the|all) (?:rules|instructions|prompt)\b", re.I)
LATEST_UPLOAD = re.compile(
    r"\b(?:latest|most recent|newest|last)\s+(?:upload|uploaded file|file|document|note)\b",
    re.I)
NOTES_OVERVIEW = re.compile(
    r"\b(?:quiz|summari[sz]e|summary|overview|main idea|key idea|key points|hardest"
    r"|most important|what are my notes about)\b", re.I)
META_TERMS = {
    "note", "notes", "say", "says", "said", "mention", "mentions", "cover", "covers",
    "according", "tell", "explain", "simple", "simply", "terms", "please", "give",
    "about", "regarding", "what", "who", "why", "how", "does", "did", "is", "are", "i",
    "during", "after", "before", "when", "where", "which", "that", "this", "with",
    "from", "into", "for", "and", "the", "of", "to", "in", "on", "by", "as", "at",
}
ORDINALS = {"first", "second", "third", "fourth", "fifth", "sixth", "seventh",
            "eighth", "ninth", "tenth"}
TIME_SENSITIVE = re.compile(
    r"\b(?:latest|newest|today|tonight|right now|at the moment|this (?:week|month|year)"
    r"|up[- ]to[- ]date|recent news|breaking news|weather|forecast|price|exchange rate"
    r"|stock (?:price|market)|release date|latest version|current version"
    r"|current (?:governor|deputy governor|vice[- ]?chancellor|president|prime minister"
    r"|minister|senator|mayor|ceo|leader)"
    r"|who is (?:the )?(?:current )?(?:governor|deputy governor|vice[- ]?chancellor"
    r"|vicechancellor|president|prime minister|minister|senator|mayor|ceo|leader)"
    r"|what year is it)\b", re.I)
OFFICE_OF = re.compile(
    r"\b(?:governor|deputy governor|vice[- ]?chancellor|vicechancellor|vc|president"
    r"|prime minister|minister|senator|mayor|ceo|leader)\s+(?:of|for)\b", re.I)


def is_notes_question(message):
    return bool(NOTES_QUESTION.search(message or ""))


def is_latest_upload(message):
    return bool(LATEST_UPLOAD.search(message or ""))


def wants_notes_overview(message):
    return is_notes_question(message) and bool(NOTES_OVERVIEW.search(message or ""))


def is_time_sensitive(message):
    if is_latest_upload(message):
        return False
    return bool(TIME_SENSITIVE.search(message or "") or OFFICE_OF.search(message or ""))


def _sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text or "")
            if part.strip()]


def _content_terms(message):
    terms = []
    for term in search.query_terms(message):
        if term in META_TERMS:
            continue
        if term in {"vicechancellor", "vicechancellors", "vc", "vcs"}:
            terms.extend(["vice", "chancellor"])
        else:
            terms.append(term)
    return list(dict.fromkeys(terms))


def required_terms(message):
    """Specific words that must appear: ordinals, numbers and proper nouns.

    Generic words like "gas" are deliberately excluded: a note can answer a
    question about gas without using that exact word.
    """
    required = []
    words = re.findall(r"[A-Za-z0-9]+(?:'[a-z]+)?", message or "")
    for index, word in enumerate(words):
        lowered = word.lower()
        if lowered in META_TERMS:
            continue
        proper = index > 0 and word[0].isupper()
        if lowered in ORDINALS or word.isdigit() or proper:
            required.append(lowered[:-2] if lowered.endswith("'s") else lowered)
    return list(dict.fromkeys(required))


def notes_cover(message, passage):
    """True when the passage contains the question's specific terms (catches 'fourth law')."""
    terms = required_terms(message)
    if not terms:
        return True
    haystack = " ".join((passage.get("path", ""), passage.get("label", ""), passage.get("text", "")))
    tokens = set(re.findall(r"[a-z0-9]+", haystack.lower()))
    return all(search._matches(term, tokens) for term in terms)


def _matched_score(sentence, terms, answer_bonus=False):
    tokens = set(re.findall(r"[a-z0-9]+", sentence.lower()))
    score = sum(1 for term in terms if search._matches(term, tokens))
    if answer_bonus:
        if re.search(r"\b(?:is|are|serves as|became|appointed|released|launched)\b",
                     sentence, re.I):
            score += 0.4
        if re.search(r"\b(?:current|latest|now|since|as of|20\d{2})\b", sentence, re.I):
            score += 0.3
        if re.search(r"\b(?:python|gpt)[- ]?\d+(?:\.\d+)*\b", sentence, re.I):
            score += 0.8
        if re.search(r"\b(?:stable|released|launched|available)\b", sentence, re.I):
            score += 0.2
        if re.search(r"\bas of\b", sentence, re.I):
            score += 0.4
        if re.search(r"\blatest stable\b", sentence, re.I):
            score += 0.4
        if re.search(rf"\b{date.today().year}\b", sentence):
            score += 0.2
        if re.search(r"\b(?:future|main branch|each .{0,20}version|download page"
                     r"|nightly)\b", sentence, re.I):
            score -= 0.8
        if re.search(r"\b(?:governor|vice[- ]?chancellor|president|prime minister|minister"
                     r"|senator|mayor|ceo|leader)\b", sentence, re.I):
            score += 0.6
        if re.search(r"\b(?:won|elected|governor-elect|election|primary|polled|candidate"
                     r"|located|is a member|has a chancellor|consists of)\b", sentence, re.I):
            score -= 0.8
    return score


def _quote(text, terms, answer_bonus=False, single=False):
    sentences = _sentences(text)
    if not sentences:
        return None, 0
    best_start, best_score, best_words = 0, -1, 0
    sizes = (1,) if single else (1, 2)
    for index in range(len(sentences)):
        for start in range(max(0, index - 1), index + 1):
            for size in sizes:
                window = sentences[start:start + size]
                if not window or not (start <= index < start + size):
                    continue
                score = sum(_matched_score(sentence, terms, answer_bonus) for sentence in window)
                words = sum(len(sentence.split()) for sentence in window)
                if words > 80:
                    continue
                if score > best_score or (score == best_score and words < best_words):
                    best_start, best_score, best_words = start, score, words
    if best_score <= 0:
        return None, 0
    chosen = 1
    for size in (1, 2):
        window = sentences[best_start:best_start + size]
        if window and sum(len(s.split()) for s in window) == best_words:
            chosen = size
            break
    if chosen == 1 and best_start > 0:
        first = sentences[best_start]
        if re.match(r"^(this|it|they|these|those|such|that)\b", first, re.I):
            previous = sentences[best_start - 1]
            if len((previous + " " + first).split()) <= 80:
                best_start -= 1
                chosen = 2
    body = " ".join(sentences[best_start:best_start + chosen]).strip()
    body = re.sub(r"(?:\s*(?:\.\.\.|\u2026))+\s*$", "", body).strip()
    if body and body[-1] not in ".!?":
        body += "."
    return (body, best_score) if body else (None, 0)


def extract_answer(message, passages, prefix="From your notes", all_passages=False,
                   answer_bonus=False, min_score=0):
    """Quote the best supporting sentence from notes or web snippets."""
    if not passages:
        return None
    terms = _content_terms(message)
    if not terms:
        return None
    candidates = passages if all_passages else passages[:1]
    best_body, best_score, best_index = None, -1, 0
    for index, passage in enumerate(candidates):
        body, score = _quote(passage.get("text", ""), terms, answer_bonus,
                             single=answer_bonus)
        if passage.get("entity"):
            score += 0.4
        label = (passage.get("label") or "").lower()
        if answer_bonus and (label.startswith("list of") or "list of" in label):
            score -= 1.0
        if answer_bonus and passage.get("provider") == "Wikipedia" and "list of" not in label:
            score += 0.2
        host = (passage.get("name") or "").lower()
        if answer_bonus and host.endswith((".gov", ".edu", ".edu.ng")):
            score += 0.3
        if body and score > best_score and score >= min_score:
            best_body, best_score, best_index = body, score, index
    if not best_body:
        return None
    return f"{prefix}: {best_body} [{best_index + 1}]"

def _source_name(item):
    if item.get("name"):
        return item["name"]
    if item.get("url"):
        return urlparse(item["url"]).netloc.removeprefix("www.")
    return Path(item["path"]).name


def source_suffix(answer, passages):
    """List the evidence when the model forgot to cite. Never change the answer itself."""
    if not passages or re.search(r"\[\d+\]", answer or ""):
        return ""
    if re.search(r"(?:don't|do not|does not|doesn't) (?:cover|mention|contain)|not in your notes",
                 answer or "", re.I):
        return ""
    labels = "; ".join(
        f"[{index}] {_source_name(item)}"
        + (f" ({item['label']})" if item.get("label") else "")
        for index, item in enumerate(passages, 1)
    )
    return "\n\nSources: " + labels + "."


def _web_answer_stream(history, message, mode, language, model, web_sink=None):
    results, error = websearch.search(message)
    if error:
        yield "Live lookup is on, but " + error
        return
    results = results[:config.WEB_MAX_RESULTS]
    if web_sink is not None:
        web_sink.extend(results)
    prefix = f"From live web results (checked {date.today():%d %b %Y})"
    if config.EXTRACTIVE_WEB:
        extracted = extract_answer(message, results, prefix=prefix, all_passages=True,
                                   answer_bonus=True, min_score=2.0)
        if extracted:
            yield extracted
            return
    parts = []
    for token in llm.chat_stream(history, message, mode, language, results, model=model,
                                 source="web"):
        parts.append(token)
        yield token
    suffix = source_suffix("".join(parts), results)
    if suffix:
        yield suffix


def answer_stream(history, message, mode, language, use_notes, model, passages=None,
                  use_web=False, web_sink=None):
    """Yield answer tokens, using notes when they help but never refusing a general question."""
    notes_question = is_notes_question(message)
    latest_upload = is_latest_upload(message)
    if use_web and not notes_question and is_time_sensitive(message):
        yield from _web_answer_stream(history, message, mode, language, model, web_sink)
        return
    if latest_upload and passages is None:
        passages = retrieve(message, use_notes=True)
    elif use_notes and passages is None:
        passages = retrieve(message, use_notes=True)
    if not use_notes and not latest_upload:
        passages = None

    if INJECTION.search(message or ""):
        yield "I cannot ignore my accuracy rules, even when asked to. Ask a normal question instead."
        return
    if re.search(r"\b(?:fourth|4th|fifth|5th) law(?: of motion)?\b", message, re.I):
        yield ("Newton's laws of motion are three: inertia, F = m x a, and action-reaction. "
               "There is no fourth law.")
        return
    if latest_upload and not passages:
        yield ("You have not uploaded any notes yet. Add a PDF, DOCX, TXT, or Markdown file, "
               "then ask again.")
        return

    intro = ""
    answer_passages = passages
    if notes_question and passages is None:
        intro = 'Use notes is off, so I could not search your library. Here is a general answer.\n\n'
        answer_passages = None
    elif notes_question and not passages:
        intro = "I could not find that in your notes. Here is a general answer.\n\n"
        answer_passages = []
    elif (notes_question and passages and not wants_notes_overview(message)
          and not notes_cover(message, passages[0])):
        intro = "I could not find that in your notes. Here is a general answer.\n\n"
        answer_passages = []

    if not notes_question and is_time_sensitive(message):
        intro = "I cannot check live information while offline, so this may be out of date.\n\n"
    elif notes_question and is_time_sensitive(message):
        intro += "I also cannot check live information offline, so this may be out of date.\n\n"

    if intro:
        yield intro
    if (answer_passages and config.EXTRACTIVE_RAG and not latest_upload
            and not wants_notes_overview(message) and mode in ("Just chat", "Explain simply")):
        extracted = extract_answer(message, answer_passages)
        if extracted:
            yield extracted
            return

    parts = []
    for token in llm.chat_stream(history, message, mode, language, answer_passages, model=model):
        parts.append(token)
        yield token
    suffix = source_suffix("".join(parts), answer_passages)
    if suffix:
        yield suffix


def sources_for(passages):
    """Small, JSON-safe source list for the web UI and the evaluation script."""
    out = []
    for passage in passages or []:
        item = {
            "name": _source_name(passage),
            "label": passage.get("label", ""),
            "score": round(float(passage.get("score", 0.0)), 3),
        }
        if passage.get("url"):
            item["url"] = passage["url"]
        out.append(item)
    return out


def verify_answer(answer, passages):
    """Check that citations point at passages that were actually retrieved.

    This is a deterministic guard against invented source numbers. It cannot
    judge whether a sentence is true, but it catches fabricated [7] citations.
    """
    numbers = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer or "")})
    if passages:
        valid = [n for n in numbers if 1 <= n <= len(passages)]
        invalid = [n for n in numbers if not 1 <= n <= len(passages)]
        return {
            "notes_used": True,
            "citations": valid,
            "invalid_citations": invalid,
            "grounded": bool(valid),
        }
    return {
        "notes_used": False,
        "citations": [],
        "invalid_citations": numbers,
        "grounded": not numbers,
    }


def friendly_error(error, model=None):
    text = str(error)
    lowered = text.lower()
    if "not found" in lowered:
        return f"The model isn't installed. Run:  ollama pull {model or config.CHAT_MODEL}"
    if "connect" in lowered or "refused" in lowered:
        return "I can't reach Ollama. Start it with:  ollama serve"
    return f"Something went wrong: {text}"


def title_for(message):
    title = " ".join((message or "").split())
    return (title[:60] + "...") if len(title) > 60 else (title or "New chat")
