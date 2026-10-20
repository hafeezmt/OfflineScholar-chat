"""Find the best passages for a question."""
import config
import llm
import store


def find(question, con=None, embed_fn=None):
    con = con or store.connect()
    qvec = None
    if config.USE_EMBEDDINGS and store.has_any_embeddings(con):
        try:
            qvec = (embed_fn or llm.embed)([question], query=True)[0]
        except TypeError:
            qvec = embed_fn([question])[0]
        except Exception:
            qvec = None  # fall back to keyword search
    return store.hybrid_search(con, question, qvec, config.TOP_K)
