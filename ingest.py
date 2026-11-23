"""Read files from the library folder, split them into chunks and index them."""
import hashlib
import re
import xml.etree.ElementTree as ET
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
            root = ET.fromstring(z.read("word/document.xml"))
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = []
        for paragraph in root.iter(f"{namespace}p"):
            pieces = []
            for element in paragraph.iter():
                if element.tag == f"{namespace}t":
                    pieces.append(element.text or "")
                elif element.tag == f"{namespace}tab":
                    pieces.append("\t")
                elif element.tag in (f"{namespace}br", f"{namespace}cr"):
                    pieces.append("\n")
            paragraphs.append("".join(pieces))
        return [("full text", "\n".join(paragraphs))]
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


def chunk_text(text, size=None, overlap=None):
    """Chunk by paragraphs first so a note stays with its context.

    Short paragraphs are packed together up to `size` words. A single oversized
    paragraph (or a PDF page with no blank lines) falls back to word windows.
    """
    size = max(1, size or config.CHUNK_WORDS)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text or "") if p.strip()]
    if not paragraphs:
        return []
    if len(paragraphs) == 1:
        return chunk_words(paragraphs[0], size=size, overlap=overlap)

    chunks = []
    current = []
    min_paragraph = min(35, size)
    for paragraph in paragraphs:
        words = paragraph.split()
        if len(words) >= min_paragraph:
            if current and len(current) + len(words) <= size:
                current.extend(words)
                chunks.append(" ".join(current))
                current = []
            elif current:
                chunks.append(" ".join(current))
                current = []
                if len(words) <= size:
                    chunks.append(paragraph)
                else:
                    chunks.extend(chunk_words(paragraph, size=size, overlap=overlap))
            elif len(words) <= size:
                chunks.append(paragraph)
            else:
                chunks.extend(chunk_words(paragraph, size=size, overlap=overlap))
            continue
        if current and len(current) + len(words) > size:
            chunks.append(" ".join(current))
            current = []
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return chunks


def index_signature(embed_fn=None):
    return "chunks-v5|{}|{}|{}".format(
        config.CHUNK_WORDS,
        config.CHUNK_OVERLAP,
        config.EMBED_MODEL if embed_fn is not None else "keyword",
    )


def library_files(folder=None):
    folder = Path(folder or config.LIBRARY_DIR)
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in config.SUPPORTED)


def _content_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_library(con, embed_fn=None, folder=None):
    """Index new or changed files. embed_fn(list_of_texts) -> list of vectors (optional)."""
    notes, added, skipped = [], 0, 0
    files = library_files(folder)
    on_disk = {str(p) for p in files}

    signature = index_signature(embed_fn)
    if store.get_meta(con, "index_signature") != signature:
        had_index = con.execute("SELECT 1 FROM files LIMIT 1").fetchone() is not None
        store.clear_index(con)
        store.set_meta(con, "index_signature", signature)
        con.commit()
        if had_index:
            notes.append("Rebuilt the note index with the improved chunking.")

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
        try:
            st = p.stat()
            digest = _content_digest(p)
        except OSError as e:
            store.remove_file(con, str(p))
            notes.append(f"Could not read {p.name}: {e}")
            continue
        row = con.execute(
            "SELECT digest,has_emb FROM files WHERE path=?", (str(p),)
        ).fetchone()
        unchanged = row and row[0] == digest
        if unchanged and (row[1] or not embed_ok):
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
            chunks = chunk_text(text)
            for number, c in enumerate(chunks, start=1):
                part = label if len(chunks) == 1 else f"{label} (part {number})"
                pieces.append((part, c))
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
        con.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?)",
                    (str(p), st.st_mtime, st.st_size, 1 if vectors[0] is not None else 0, digest))
        added += 1
    con.commit()
    if embed_fn is not None and embed_ok:
        store.set_meta(con, "embed_model", config.EMBED_MODEL)
        con.commit()
    msg = f"Indexed {added} new or changed file(s), {skipped} unchanged, {len(files)} total."
    return " ".join([msg] + notes)
