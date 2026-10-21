"""SQLite storage + search (keyword with FTS5, meaning-based with embeddings, or both)."""
import re
import sqlite3
import time
from array import array

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
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS conversations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            created REAL NOT NULL,
            updated REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, id);
        """
    )
    return con


def remove_file(con, path):
    ids = [r[0] for r in con.execute("SELECT id FROM chunks WHERE path=?", (path,))]
    for i in ids:
        con.execute("DELETE FROM chunks_fts WHERE rowid=?", (i,))
    con.execute("DELETE FROM chunks WHERE path=?", (path,))
    con.execute("DELETE FROM files WHERE path=?", (path,))


def _normalise(values):
    vector = [float(value) for value in values]
    norm = sum(value * value for value in vector) ** 0.5
    return [value / norm for value in vector] if norm else vector


def add_chunks(con, path, rows):
    """rows: list of (label, text, vector_or_None)"""
    for label, text, vec in rows:
        blob = None
        if vec is not None:
            blob = array("f", _normalise(vec)).tobytes()
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
    query = _normalise(qvec)
    if not query:
        return []
    # Vectors indexed with a different embedding model have another size; skip them.
    rows = [r for r in rows if len(r[4]) == len(query) * 4]
    if not rows:
        return []
    scores = []
    for row in rows:
        vector = array("f")
        vector.frombytes(row[4])
        if len(vector) != len(query):
            continue
        score = sum(left * right for left, right in zip(query, vector))
        scores.append((score, row))
    scores.sort(key=lambda item: item[0], reverse=True)
    return [dict(id=row[0], path=row[1], label=row[2], text=row[3], score=float(score))
            for score, row in scores[:k] if score > 0.15]


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


def create_conversation(con, title):
    now = time.time()
    cur = con.execute("INSERT INTO conversations(title, created, updated) VALUES (?,?,?)",
                      (title, now, now))
    con.commit()
    return cur.lastrowid


def conversation_exists(con, conversation_id):
    return con.execute("SELECT 1 FROM conversations WHERE id=?", (conversation_id,)).fetchone() is not None


def list_conversations(con, limit=100):
    rows = con.execute(
        """
        SELECT c.id, c.title, c.updated,
               (SELECT m.content FROM messages m WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1)
        FROM conversations c
        ORDER BY c.updated DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [{"id": r[0], "title": r[1], "updated": r[2], "preview": (r[3] or "")[:140]} for r in rows]


def conversation_messages(con, conversation_id, limit=None):
    sql = "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id"
    rows = con.execute(sql, (conversation_id,)).fetchall()
    if limit:
        rows = rows[-limit:]
    return [{"role": r[0], "content": r[1]} for r in rows]


def append_message(con, conversation_id, role, content):
    now = time.time()
    con.execute("INSERT INTO messages(conversation_id, role, content, created) VALUES (?,?,?,?)",
                (conversation_id, role, content, now))
    con.execute("UPDATE conversations SET updated=? WHERE id=?", (now, conversation_id))
    con.commit()


def rename_conversation(con, conversation_id, title):
    con.execute("UPDATE conversations SET title=?, updated=? WHERE id=?",
                (title, time.time(), conversation_id))
    con.commit()


def delete_conversation(con, conversation_id):
    con.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
    con.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    con.commit()


def get_meta(con, key, default=None):
    row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_meta(con, key, value):
    con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))


def drop_embeddings(con):
    """Forget every stored vector, for example after switching embedding models."""
    con.execute("UPDATE chunks SET emb=NULL")
    con.execute("UPDATE files SET has_emb=0")


def clear_index(con):
    """Drop everything that was indexed. The files on disk are left alone."""
    con.execute("DELETE FROM chunks_fts")
    con.execute("DELETE FROM chunks")
    con.execute("DELETE FROM files")
    con.commit()


def has_any_embeddings(con):
    return con.execute("SELECT 1 FROM chunks WHERE emb IS NOT NULL LIMIT 1").fetchone() is not None
