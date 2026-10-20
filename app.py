"""OfflineScholar: chat with an AI with NO internet. Gemma 4 runs locally through Ollama.
Optional: add your own notes and let it search them (Snowflake Arctic Embed, also local)."""
import shutil
from pathlib import Path

import gradio as gr

import config
import ingest
import llm
import search
import store
import webpages

config.LIBRARY_DIR.mkdir(exist_ok=True)

OLLAMA_HELP = "I can't reach Ollama. Start it in another terminal with:  ollama serve"


def normalize_history(history):
    """Gradio versions send history in different shapes. Turn it into role/content dicts."""
    msgs = []
    for h in history or []:
        if isinstance(h, dict):
            content = h.get("content", "")
            if isinstance(content, list):
                content = " ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
            if content:
                msgs.append({"role": h.get("role", "user"), "content": content})
        else:
            user, bot = h
            if user:
                msgs.append({"role": "user", "content": user})
            if bot:
                msgs.append({"role": "assistant", "content": bot})
    return msgs


def chat(message, history, mode, language, use_notes):
    if isinstance(message, dict):
        message = message.get("text", "")
    passages = []
    if use_notes:
        try:
            passages = search.find(message)
        except Exception:
            passages = []
    text = ""
    try:
        for token in llm.chat_stream(normalize_history(history), message, mode, language, passages):
            text += token
            yield text
    except Exception as e:
        err = str(e).lower()
        if "not found" in err:
            note = f"The model isn't installed. Run:  ollama pull {config.CHAT_MODEL}"
        elif "connect" in err or "refused" in err:
            note = OLLAMA_HELP
        else:
            note = f"Something went wrong: {e}"
        yield (text + "\n\n" + note).strip()
        return
    if passages:
        text += "\n\n*From your notes:* " + ", ".join(
            f"[{i}] {p['path'].split('/')[-1]} ({p['label']})" for i, p in enumerate(passages, 1))
        yield text


def rescan():
    con = store.connect()
    try:
        return ingest.scan_library(con, embed_fn=llm.embed if config.USE_EMBEDDINGS else None)
    except Exception as e:
        return f"Re-scan problem: {e}"
    finally:
        con.close()


def add_files(files):
    if not files:
        return "Choose one or more files first."
    config.LIBRARY_DIR.mkdir(exist_ok=True)
    copied, updated, skipped, problems = 0, [], [], []
    for f in files:
        src = Path(f if isinstance(f, str) else f.name)
        if not src.is_file():
            problems.append(f"{src.name} was not found")
            continue
        if src.suffix.lower() not in config.SUPPORTED:
            problems.append(f"{src.name} is not a supported type")
            continue
        dest = config.LIBRARY_DIR / src.name
        try:
            if src.resolve() == dest.resolve():
                skipped.append(src.name)
                continue
            if dest.exists():
                if dest.read_bytes() == src.read_bytes():
                    skipped.append(src.name)
                    continue
                updated.append(src.name)
            shutil.copyfile(src, dest)
            copied += 1
        except OSError as e:
            problems.append(f"{src.name}: {e}")
    msg = f"Added {copied} file(s)."
    if updated:
        msg += f" Updated: {', '.join(updated)}."
    if skipped:
        msg += f" Already in library: {', '.join(skipped)}."
    if problems:
        msg += " " + "; ".join(problems) + "."
    return msg + "\n" + rescan()


def save_url(url):
    msg = webpages.save_page(url)
    return msg + ("\n" + rescan() if msg.startswith("Saved") else "")


def clear_index():
    con = store.connect()
    try:
        store.clear_index(con)
    except Exception as e:
        return f"Could not clear the index: {e}"
    finally:
        con.close()
    return "Index cleared. Your files are still in the library; press Re-scan library to index them again."


def library_list():
    files = ingest.library_files()
    return "\n".join(f"- {p.name}" for p in files) or "No files yet."


with gr.Blocks(title="OfflineScholar") as demo:
    gr.Markdown(
        "# OfflineScholar\nChat with an AI for your studies, **with no internet**. "
        f"Running locally: `{config.CHAT_MODEL}`."
    )
    with gr.Tab("Chat"):
        gr.ChatInterface(
            fn=chat,
            additional_inputs=[
                gr.Dropdown(list(llm.MODES), value="Just chat", label="Study mode", render=False),
                gr.Dropdown(list(llm.LANGUAGES), value="English", label="Language", render=False),
                gr.Checkbox(value=False, label="Also search my notes (Library tab)", render=False),
            ],
        )
    with gr.Tab("My notes (optional)"):
        gr.Markdown("Add your notes, PDFs or saved pages. Tick **Also search my notes** in the Chat tab "
                    "and the AI will use them. Search uses Snowflake Arctic Embed, locally.")
        files_md = gr.Markdown(library_list())
        upload = gr.File(label="Add notes (.pdf, .docx, .txt, .md)", file_count="multiple")
        add_btn = gr.Button("Add files")
        scan_btn = gr.Button("Re-scan library")
        clear_btn = gr.Button("Clear index (keeps files)")
        url = gr.Textbox(label="Save a web page for offline (needs internet once)", placeholder="https://...")
        save_btn = gr.Button("Save page")
        status = gr.Markdown()
        add_btn.click(add_files, upload, status).then(library_list, None, files_md)
        scan_btn.click(rescan, None, status).then(library_list, None, files_md)
        clear_btn.click(clear_index, None, status)
        save_btn.click(save_url, url, status).then(library_list, None, files_md)
        demo.load(library_list, None, files_md)

if __name__ == "__main__":
    demo.launch()
