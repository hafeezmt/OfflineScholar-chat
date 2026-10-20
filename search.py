"""Find the best passages for a question."""
import inspect

import config
import llm
import store


def _accepts_query_arg(embed_fn):
    """True when the embedding function takes a `query` keyword (the real model does)."""
    try:
        params = inspect.signature(embed_fn).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(p.name == "query" or p.kind == p.VAR_KEYWORD for p in params)


def find(question, con=None, embed_fn=None):
    owned = con is None
    con = con or store.connect()
    try:
        qvec = None
        if config.USE_EMBEDDINGS and store.has_any_embeddings(con):
            embed = embed_fn or llm.embed
            try:
                if _accepts_query_arg(embed):
                    qvec = embed([question], query=True)[0]
                else:
                    qvec = embed([question])[0]
            except Exception:
                qvec = None  # fall back to keyword search
        return store.hybrid_search(con, question, qvec, config.TOP_K)
    finally:
        if owned:
            con.close()
