"""Quick check that indexing and search work. Does not need Ollama or internet."""
import hashlib
import tempfile
from pathlib import Path

import config
import ingest
import search
import store


def fake_embed(texts, query=False):
    """Stand-in for the real embedding model: hashes words into a small vector."""
    out = []
    for t in texts:
        v = [0.0] * 64
        for w in t.lower().split():
            v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
        out.append(v)
    return out


def run():
    with tempfile.TemporaryDirectory() as tmp:
        con = store.connect(Path(tmp) / "t.db")
        try:
            print(ingest.scan_library(con))                      # keyword only
            print(ingest.scan_library(con))                      # second run: nothing new
            hits = search.find("What is photosynthesis and chlorophyll?", con=con)
            assert hits and "photosynthesis" in hits[0]["path"], hits
            print("Keyword search OK ->", Path(hits[0]["path"]).name)

            print(ingest.scan_library(con, embed_fn=fake_embed))  # adds embeddings
            hits = search.find("force equals mass times acceleration", con=con, embed_fn=fake_embed)
            assert hits and "newton" in hits[0]["path"], hits
            print("Hybrid search OK ->", Path(hits[0]["path"]).name)

            none = store.keyword_search(con, "zebra spaceship quantum", 4)
            assert none == [], none
            print("Unrelated question finds nothing OK")
        finally:
            con.close()
    print("All checks passed.")


if __name__ == "__main__":
    if not config.LIBRARY_DIR.exists():
        raise SystemExit(f"Sample notes not found in {config.LIBRARY_DIR}")
    run()
