# ingest.py
"""Ingest documents into SQLite FTS5 database.
Supports .txt, .md, .pdf, .docx files.
Chunks are ~300 words with source metadata.
"""
import os
import sqlite3
from pathlib import Path
import hashlib
import nltk
from nltk.tokenize import word_tokenize
from pypdf import PdfReader
import docx
import json

nltk.download('punkt', quiet=True)

from config import LIBRARY_PATH, DB_PATH

CHUNK_WORD_COUNT = 300

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            mtime REAL,
            hash TEXT
        );
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
            content,
            path,
            chunk_index,
            source_section,
            tokenize='porter'
        );
    """)
    return conn

def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def split_into_chunks(text: str, source_section: str):
    """Split raw text into ~300‑word chunks.
    We avoid NLTK's heavyweight tokenizer to keep the environment lightweight.
    Simple whitespace split works fine for our offline use‑case.
    """
    words = text.split()
    chunks = []
    for i in range(0, len(words), CHUNK_WORD_COUNT):
        chunk_words = words[i:i + CHUNK_WORD_COUNT]
        chunk_text = " ".join(chunk_words)
        chunks.append((chunk_text, source_section, i // CHUNK_WORD_COUNT + 1))
    return chunks

def extract_text_from_file(file_path: Path):
    suffix = file_path.suffix.lower()
    if suffix in ['.txt', '.md']:
        return file_path.read_text(encoding='utf-8')
    if suffix == '.pdf':
        try:
            reader = PdfReader(str(file_path))
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                pages.append((text, f"Page {i+1}"))
            return pages
        except Exception as e:
            print(f"Failed PDF {file_path}: {e}")
            return []
    if suffix == '.docx':
        try:
            doc = docx.Document(str(file_path))
            full = []
            for i, para in enumerate(doc.paragraphs):
                full.append((para.text, f"Paragraph {i+1}"))
            return full
        except Exception as e:
            print(f"Failed DOCX {file_path}: {e}")
            return []
    return []

def ingest_file(conn, file_path: Path):
    mtime = file_path.stat().st_mtime
    cur = conn.execute("SELECT mtime FROM documents WHERE path = ?", (str(file_path),))
    row = cur.fetchone()
    if row and row[0] == mtime:
        return  # unchanged
    # Remove old entries
    conn.execute("DELETE FROM passages WHERE path = ?", (str(file_path),))
    conn.execute("DELETE FROM documents WHERE path = ?", (str(file_path),))
    # Process new content
    content = extract_text_from_file(file_path)
    if isinstance(content, str):
        chunks = split_into_chunks(content, "Full")
        for txt, sec, idx in chunks:
            conn.execute(
                "INSERT INTO passages (content, path, chunk_index, source_section) VALUES (?,?,?,?)",
                (txt, str(file_path), idx, sec)
            )
    else:  # list of (text, section)
        for txt, sec in content:
            chunks = split_into_chunks(txt, sec)
            for txt_chunk, sec2, idx in chunks:
                conn.execute(
                    "INSERT INTO passages (content, path, chunk_index, source_section) VALUES (?,?,?,?)",
                    (txt_chunk, str(file_path), idx, sec2)
                )
    conn.execute("INSERT INTO documents (path, mtime, hash) VALUES (?,?,?)", (str(file_path), mtime, compute_hash(str(file_path))))
    conn.commit()

def scan_library():
    conn = get_connection()
    lib_path = Path(LIBRARY_PATH)
    for ext in ['**/*.txt', '**/*.md', '**/*.pdf', '**/*.docx']:
        for file_path in lib_path.glob(ext):
            ingest_file(conn, file_path)
    conn.close()

if __name__ == "__main__":
    scan_library()
    print("Library indexed.")
