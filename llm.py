"""All calls to the local Ollama server (Gemma 4 for chat, Snowflake Arctic Embed for searching notes)."""
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


def embed(texts, query=False):
    prefix = config.QUERY_PREFIX if query else ""
    resp = ollama.embed(model=config.EMBED_MODEL, input=[prefix + t for t in texts])
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


def chat_stream(history, message, mode="Just chat", language="English", passages=None):
    """history: list of {"role","content"} dicts. Yields the reply piece by piece."""
    system = f"{BASE_SYSTEM}\n{MODES.get(mode, MODES['Just chat'])} {LANGUAGES.get(language, LANGUAGES['English'])}"
    if passages:
        context = "\n\n".join(
            f"[{i}] ({p['path'].split('/')[-1]}, {p['label']})\n{p['text']}" for i, p in enumerate(passages, 1)
        )
        system += (
            "\n\nThe student's own notes are below. Use them when they are relevant and mention the "
            f"passage number like [1]. If they are not relevant, answer normally.\n\nNOTES:\n{context}"
        )
    messages = [{"role": "system", "content": system}] + trim_history(history, config.HISTORY_LIMIT) + [
        {"role": "user", "content": message}]
    stream = ollama.chat(
        model=config.CHAT_MODEL,
        messages=messages,
        stream=True,
        options={"num_ctx": config.NUM_CTX, "temperature": config.TEMPERATURE},
    )
    for part in stream:
        yield part["message"]["content"]
