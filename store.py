"""SQLite storage + search (keyword with FTS5, meaning-based with embeddings, or both)."""
import re
import sqlite3

import numpy as np

import config

STOP = set("a an the is are was were be of to in on at for and or what why how who when where which "
           "does do did can could would should explain tell me about with from by it this that these those "
           "as into your you i my we our their".split())


def connect(db_path=None):
    con = sqlite3.connect(str(db_path or config.DB_PATH), timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("PRAGMA busy_timeout=5000")
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS files(path TEXT PRIMARY KEY, mtime REAL, size INTEGER, has_emb INTEGER);
        CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, label TEXT,
                                          text TEXT, emb BLOB);
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text);
        CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path);
        """
    )
    return con


def remove_file(con, path):
    ids = [r[0] for r in con.execute("SELECT id FROM chunks WHERE path=?", (path,))]
    for i in ids:
        con.execute("DELETE FROM chunks_fts WHERE rowid=?", (i,))
    con.execute("DELETE FROM chunks WHERE path=?", (path,))
    con.execute("DELETE FROM files WHERE path=?", (path,))


def add_chunks(con, path, rows):
    """rows: list of (label, text, vector_or_None)"""
    for label, text, vec in rows:
        blob = None
        if vec is not None:
            v = np.asarray(vec, dtype=np.float32)
            n = np.linalg.norm(v)
            blob = (v / n if n else v).tobytes()
        cur = con.execute("INSERT INTO chunks(path,label,text,emb) VALUES (?,?,?,?)", (path, label, text, blob))
        con.execute("INSERT INTO chunks_fts(rowid,text) VALUES (?,?)", (cur.lastrowid, text))


def keyword_search(con, query, k):
    words = [w for w in re.findall(r"\w{2,}", query.lower()) if w not in STOP]
    if not words:
        return []
    match = " OR ".join(f'"{w}"' for w in words)
    sql = (
        "SELECT c.id,c.path,c.label,c.text FROM chunks_fts "
        "JOIN chunks c ON c.id=chunks_fts.rowid "
        "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?"
    )
    return [dict(id=r[0], path=r[1], label=r[2], text=r[3]) for r in con.execute(sql, (match, k))]


def semantic_search(con, qvec, k):
    rows = con.execute("SELECT id,path,label,text,emb FROM chunks WHERE emb IS NOT NULL").fetchall()
    if not rows:
        return []
    q = np.asarray(qvec, dtype=np.float32).ravel()
    n = np.linalg.norm(q)
    q = q / n if n else q
    # Vectors indexed with a different embedding model have another size; skip them
    # instead of crashing numpy when stacking.
    rows = [r for r in rows if len(r[4]) == q.size * 4]
    if not rows:
        return []
    mat = np.stack([np.frombuffer(r[4], dtype=np.float32) for r in rows])
    scores = mat @ q
    order = np.argsort(-scores)[:k]
    return [dict(id=rows[i][0], path=rows[i][1], label=rows[i][2], text=rows[i][3]) for i in order
            if scores[i] > 0.15]


def hybrid_search(con, query, qvec, k):
    """Combine keyword and meaning-based results (reciprocal rank fusion)."""
    kw = keyword_search(con, query, k * 2)
    sem = semantic_search(con, qvec, k * 2) if qvec is not None else []
    if not sem:
        return kw[:k]
    scores, items = {}, {}
    for lst in (kw, sem):
        for rank, item in enumerate(lst):
            scores[item["id"]] = scores.get(item["id"], 0) + 1.0 / (60 + rank)
            items[item["id"]] = item
    best = sorted(scores, key=scores.get, reverse=True)[:k]
    return [items[i] for i in best]


def clear_index(con):
    """Drop everything that was indexed. The files on disk are left alone."""
    con.execute("DELETE FROM chunks_fts")
    con.execute("DELETE FROM chunks")
    con.execute("DELETE FROM files")
    con.commit()


def has_any_embeddings(con):
    return con.execute("SELECT 1 FROM chunks WHERE emb IS NOT NULL LIMIT 1").fetchone() is not None
