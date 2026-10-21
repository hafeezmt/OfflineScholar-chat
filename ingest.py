"""Read files from the library folder, split them into chunks and index them."""
import html
import re
import zipfile
from pathlib import Path

import config
import store


def read_sections(path: Path):
    """Return a list of (label, text) sections for a file."""
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return [("full text", path.read_text(encoding="utf-8", errors="ignore"))]
    if ext == ".pdf":
        from pypdf import PdfReader

        out = []
        for i, page in enumerate(PdfReader(str(path)).pages, start=1):
            try:
                out.append((f"page {i}", page.extract_text() or ""))
            except Exception:
                continue
        return out
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:(?:tab|br)\s*/>", " ", xml)
        return [("full text", html.unescape(re.sub(r"<[^>]+>", "", xml)))]
    return []


def chunk_words(text, size=None, overlap=None):
    size = max(1, size or config.CHUNK_WORDS)
    overlap = config.CHUNK_OVERLAP if overlap is None else overlap
    overlap = max(0, min(overlap, size - 1))
    words = text.split()
    if not words:
        return []
    if len(words) <= size:
        return [" ".join(words)]
    step = max(1, size - overlap)
    chunks = []
    for i in range(0, len(words), step):
        chunks.append(" ".join(words[i:i + size]))
        if i + size >= len(words):
            break
    return chunks


def library_files(folder=None):
    folder = Path(folder or config.LIBRARY_DIR)
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in config.SUPPORTED)


def scan_library(con, embed_fn=None, folder=None):
    """Index new or changed files. embed_fn(list_of_texts) -> list of vectors (optional)."""
    notes, added, skipped = [], 0, 0
    files = library_files(folder)
    on_disk = {str(p) for p in files}

    for (path,) in con.execute("SELECT path FROM files").fetchall():
        if path not in on_disk:
            store.remove_file(con, path)

    embed_ok = embed_fn is not None
    if embed_ok:
        stored_model = store.get_meta(con, "embed_model")
        if stored_model != config.EMBED_MODEL:
            store.drop_embeddings(con)
            if stored_model is not None:
                notes.append(f"Embedding model changed to {config.EMBED_MODEL}; rebuilding note vectors.")
    for p in files:
        st = p.stat()
        row = con.execute("SELECT mtime,size,has_emb FROM files WHERE path=?", (str(p),)).fetchone()
        unchanged = row and row[0] == st.st_mtime and row[1] == st.st_size
        if unchanged and (row[2] or not embed_ok):
            skipped += 1
            continue
        try:
            sections = read_sections(p)
        except Exception as e:
            store.remove_file(con, str(p))
            notes.append(f"Could not read {p.name}: {e}")
            continue
        pieces = []
        for label, text in sections:
            for c in chunk_words(text):
                pieces.append((label, c))
        if not pieces:
            store.remove_file(con, str(p))
            notes.append(f"{p.name} has no readable text (scanned PDF?)")
            continue
        vectors = [None] * len(pieces)
        if embed_ok:
            try:
                vectors = []
                for i in range(0, len(pieces), 16):
                    batch = [t for _, t in pieces[i:i + 16]]
                    got = embed_fn(batch)
                    if len(got) != len(batch):
                        raise ValueError(
                            f"embedding model returned {len(got)} vectors for {len(batch)} chunks")
                    vectors.extend(got)
            except Exception as e:
                embed_ok = False
                vectors = [None] * len(pieces)
                notes.append(f"Meaning-based search is off ({e}). Using keyword search.")
        store.remove_file(con, str(p))
        store.add_chunks(con, str(p), [(l, t, v) for (l, t), v in zip(pieces, vectors)])
        con.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?)",
                    (str(p), st.st_mtime, st.st_size, 1 if vectors[0] is not None else 0))
        added += 1
    con.commit()
    if embed_fn is not None and embed_ok:
        store.set_meta(con, "embed_model", config.EMBED_MODEL)
        con.commit()
    msg = f"Indexed {added} new or changed file(s), {skipped} unchanged, {len(files)} total."
    return " ".join([msg] + notes)
