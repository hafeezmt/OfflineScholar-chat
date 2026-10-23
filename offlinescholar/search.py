"""Find the best passages for a question, rejecting irrelevant matches.

The embedding model is tiny, so unrelated notes can still score around 0.5.
Semantic-only matches therefore need a minimum score, and keyword matches need
more than one meaningful term (or one distinctive long term) before they are
trusted. This keeps RAG from injecting noise into every answer.
"""
import inspect
import re

from . import config, llm, store


def _accepts_query_arg(embed_fn):
    """True when the embedding function takes a `query` keyword (the real model does)."""
    try:
        params = inspect.signature(embed_fn).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(p.name == "query" or p.kind == p.VAR_KEYWORD for p in params)


def query_terms(question):
    """Meaningful words in a question, with a very light plural/'s normalisation."""
    terms = []
    for word in re.findall(r"[a-z0-9]+(?:'[a-z]+)?", (question or "").lower()):
        word = word[:-2] if word.endswith("'s") else word
        if len(word) < 2 or word in store.STOP:
            continue
        terms.append(word)
    return list(dict.fromkeys(terms))


def _matches(term, tokens):
    if term in tokens:
        return True
    if len(term) >= 5:
        stem = term[:5]
        return any(token.startswith(stem) for token in tokens)
    return False


def _lexical_match(item, terms):
    tokens = set(re.findall(r"[a-z0-9]+", item["text"].lower()))
    matched = [term for term in terms if _matches(term, tokens)]
    strong = len(matched) >= 2 or any(len(term) >= 9 for term in matched)
    return matched, strong


def _phrase_bonus(terms, text):
    """Reward exact two-word phrases such as "second law" or "lurch forward"."""
    normalised = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    return sum(0.08 for i in range(len(terms) - 1)
               if f"{terms[i]} {terms[i + 1]}" in normalised)


def find(question, con=None, embed_fn=None, min_score=None, limit=None):
    owned = con is None
    con = con or store.connect()
    try:
        limit = max(1, limit or config.TOP_K)
        min_score = config.RAG_MIN_SCORE if min_score is None else min_score
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

        keywords = store.keyword_search(con, question, max(limit * 3, 8))
        semantic = store.semantic_search(con, qvec, max(limit * 3, 8)) if qvec is not None else []
        terms = query_terms(question)

        candidates = {}
        lexical_ids = set()
        for item in keywords:
            matched, strong = _lexical_match(item, terms)
            if not strong:
                continue
            lexical_ids.add(item["id"])
            coverage = len(matched) / max(1, len(terms))
            score = min(1.0, round(coverage + _phrase_bonus(terms, item["text"]), 4))
            candidates[item["id"]] = dict(
                item,
                matched_terms=matched,
                match="keyword",
                score=score,
            )

        best = semantic[0]["score"] if semantic else 0.0
        for item in semantic:
            score = item["score"]
            if score < min_score or score < best - config.RAG_MIN_MARGIN:
                continue
            matched, _ = _lexical_match(item, terms)
            item = dict(item, matched_terms=matched, match="semantic",
                        score=score + _phrase_bonus(terms, item["text"]))
            if item["id"] in candidates:
                candidates[item["id"]]["score"] = max(candidates[item["id"]].get("score", 0.0),
                                                      item["score"])
            else:
                candidates[item["id"]] = item

        if not candidates:
            return []

        ranked = sorted(
            candidates.values(),
            key=lambda item: item.get("score", 0.0) + (0.1 if item["id"] in lexical_ids else 0.0),
            reverse=True,
        )
        return ranked[:limit]
    finally:
        if owned:
            con.close()
