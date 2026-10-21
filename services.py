"""Operations shared by the web API, the terminal client and the Gradio app."""
from pathlib import Path

import config
import ingest
import llm
import search
import store
import webpages

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


def answer_stream(history, message, mode, language, use_notes, model):
    """Yield answer tokens, using the notes library when requested."""
    passages = search.find(message) if use_notes else []
    yield from llm.chat_stream(history, message, mode, language, passages, model=model)


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
