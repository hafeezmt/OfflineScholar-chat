# search.py
"""Search the indexed library using SQLite FTS5 (BM25).
Optionally use embeddings via Ollama if enabled.
"""
import os
import sqlite3
from typing import List, Tuple

from config import DB_PATH, USE_EMBEDDINGS, EMBEDDING_MODEL


def get_connection():
    return sqlite3.connect(DB_PATH)


def bm25_search(query: str, top_k: int = 4) -> List[Tuple[str, str, int, str]]:
    """Return top_k passages matching the query.
    Each result is a tuple: (content, path, chunk_index, source_section).
    """
    conn = get_connection()
    # Use the BM25 ranking function provided by FTS5
    cur = conn.execute(
        "SELECT content, path, chunk_index, source_section, rank "
        "FROM passages WHERE passages MATCH ? ORDER BY rank LIMIT ?",
        (query, top_k),
    )
    results = [(row[0], row[1], row[2], row[3]) for row in cur.fetchall()]
    conn.close()
    return results

# Placeholder for embeddings search; not implemented now.

def embedding_search(_query: str, _top_k: int = 4):
    if not USE_EMBEDDINGS:
        raise RuntimeError("Embeddings are disabled in config.")
    # In a full implementation, we would compute embedding via Ollama and do a nearest neighbor search.
    raise NotImplementedError("Embedding search not implemented in this minimal version.")
