"""All calls to the local Ollama server (Gemma 4 for chat, Snowflake Arctic Embed for searching notes)."""
from pathlib import Path

import ollama

import config

LANGUAGES = {
    "English": "Reply in clear, simple English.",
    "Nigerian Pidgin": "Reply in easy Nigerian Pidgin English. Keep technical words in English.",
    "Hausa": "Reply in simple Hausa. Keep technical words in English.",
}

MODES = {
    "Just chat": "Answer the way a helpful, friendly tutor would.",
    "Explain simply": "Explain like a friendly tutor teaching a beginner, with a short everyday example.",
    "Homework helper": "Help step by step. Number the steps and explain the reasoning so the student learns.",
    "Essay / report outline": "Give a clear outline with headings and 2 to 3 bullet points under each heading.",
    "Quiz me": "Ask 5 short quiz questions on the topic, one at a time style, with answers at the end.",
    "Summarize my text": "Summarize the text the student gives you in 5 clear bullet points.",
}

BASE_SYSTEM = (
    "You are OfflineScholar, a study assistant running fully offline on a student's laptop. "
    "You help with homework, explanations, research ideas, essays, maths, science and coding. "
    "You cannot browse the internet and your knowledge may be out of date, so say so when it matters "
    "and say when you are not sure instead of guessing."
)


def list_models():
    """Names of the models installed in Ollama, or [] when Ollama is not reachable."""
    try:
        resp = ollama.list()
    except Exception:
        return []
    models = getattr(resp, "models", None)
    if models is None and isinstance(resp, dict):
        models = resp.get("models", [])
    names = []
    for m in models or []:
        name = getattr(m, "model", None)
        if name is None and isinstance(m, dict):
            name = m.get("model")
        if name:
            names.append(name)
    return sorted(set(names))


def default_model(installed=None):
    """Pick a chat model: the lite one on low-RAM machines, otherwise the configured model."""
    models = installed
    if models is None:
        models = [m for m in list_models() if "embed" not in m.lower()]
    if config.LOW_MEMORY and "gemma3:1b" in models and not config.CHAT_MODEL_EXPLICIT:
        return "gemma3:1b"
    if models and config.CHAT_MODEL not in models:
        return models[0]
    return config.CHAT_MODEL


def embed(texts, query=False):
    prefix = config.QUERY_PREFIX if query else ""
    resp = ollama.embed(model=config.EMBED_MODEL, input=[prefix + t for t in texts],
                        keep_alive=config.KEEP_ALIVE)
    return resp["embeddings"]


def trim_history(history, limit=8):
    """Keep the last few turns, starting with a user message so the model is not fed an orphan reply."""
    msgs = [m for m in (history or []) if (m.get("content") or "").strip()]
    if limit <= 0:
        return []
    msgs = msgs[-limit:]
    while msgs and msgs[0].get("role") != "user":
        msgs.pop(0)
    return msgs


def chat_stream(history, message, mode="Just chat", language="English", passages=None, model=None):
    """history: list of {"role","content"} dicts. Yields the reply piece by piece."""
    model = model or config.CHAT_MODEL
    system = f"{BASE_SYSTEM}\n{MODES.get(mode, MODES['Just chat'])} {LANGUAGES.get(language, LANGUAGES['English'])}"
    if passages:
        context = "\n\n".join(
            f"[{i}] ({Path(p['path']).name}, {p['label']})\n{p['text']}" for i, p in enumerate(passages, 1)
        )
        system += (
            "\n\nThe student's own notes are below. Use them when they are relevant and mention the "
            f"passage number like [1]. If they are not relevant, answer normally.\n\nNOTES:\n{context}"
        )
    messages = [{"role": "system", "content": system}] + trim_history(history, config.HISTORY_LIMIT) + [
        {"role": "user", "content": message}]
    stream = ollama.chat(
        model=model,
        messages=messages,
        stream=True,
        keep_alive=config.KEEP_ALIVE,
        options={
            "num_ctx": config.NUM_CTX,
            "temperature": config.TEMPERATURE,
            "num_predict": config.NUM_PREDICT,
            "num_thread": config.NUM_THREAD,
            "num_batch": config.NUM_BATCH,
        },
    )
    for part in stream:
        yield part["message"]["content"]
