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

ASSETS = config.BASE / "assets"
CSS = ""
if (ASSETS / "style.css").exists():
    CSS = (ASSETS / "style.css").read_text(encoding="utf-8")
AVATARS = (str(ASSETS / "user.svg"), str(ASSETS / "scholar.svg"))
if not all(Path(p).exists() for p in AVATARS):
    AVATARS = None

THEME = gr.themes.Soft(
    primary_hue="emerald",
    secondary_hue="teal",
    neutral_hue="slate",
    font=["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
)

# Gradio 6 moved theme and css from Blocks() to launch().
BLOCKS_KWARGS = {"title": "OfflineScholar"}
LAUNCH_KWARGS = {}
if int(gr.__version__.split(".")[0]) >= 6:
    LAUNCH_KWARGS = {"theme": THEME, "css": CSS}
else:
    BLOCKS_KWARGS.update(theme=THEME, css=CSS)

MODELS = [m for m in llm.list_models() if "embed" not in m.lower()]
DEFAULT_MODEL = llm.default_model(MODELS)
if not MODELS:
    MODELS = [DEFAULT_MODEL]

LOW_RAM_CHIP = '<span class="chip">Low-RAM mode</span>' if config.LOW_MEMORY else ""

HEADER = f"""
<div class="hero">
  <span class="eyebrow">Private &middot; Offline &middot; Free</span>
  <h1>OfflineScholar</h1>
  <p>Your study tutor that runs entirely on this laptop. Ask questions, work through homework,
  practise quizzes and search your own notes &mdash; no internet required.</p>
  <div class="chips">
    <span class="chip">Chat model: <code>{DEFAULT_MODEL}</code></span>
    <span class="chip">Notes search: <code>{config.EMBED_MODEL}</code></span>
    {LOW_RAM_CHIP}
  </div>
</div>
"""


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


def chat(message, history, mode, language, use_notes, model=None):
    if isinstance(message, dict):
        message = message.get("text", "")
    model = model or DEFAULT_MODEL
    passages = []
    if use_notes:
        try:
            passages = search.find(message)
        except Exception:
            passages = []
    text = ""
    try:
        for token in llm.chat_stream(normalize_history(history), message, mode, language, passages, model=model):
            text += token
            yield text
    except Exception as e:
        err = str(e).lower()
        if "not found" in err:
            note = f"The model isn't installed. Run:  ollama pull {model}"
        elif "connect" in err or "refused" in err:
            note = OLLAMA_HELP
        else:
            note = f"Something went wrong: {e}"
        yield (text + "\n\n" + note).strip()
        return
    if passages:
        text += "\n\n*From your notes:* " + ", ".join(
            f"[{i}] {Path(p['path']).name} ({p['label']})" for i, p in enumerate(passages, 1))
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


def _size(n):
    for unit in ("B", "KB", "MB"):
        if n < 1024 or unit == "MB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def library_list():
    files = ingest.library_files()
    if not files:
        return "No files yet."
    con = store.connect()
    try:
        indexed = {row[0]: row[1] for row in con.execute("SELECT path, has_emb FROM files")}
    finally:
        con.close()
    lines, total = [], 0
    for p in files:
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        total += size
        if str(p) not in indexed:
            state = "not indexed"
        else:
            state = "indexed with embeddings" if indexed[str(p)] else "indexed (keyword only)"
        lines.append(f"- {p.name} ({_size(size)}, {state})")
    return f"**{len(files)} file(s), {_size(total)}**\n" + "\n".join(lines)


with gr.Blocks(**BLOCKS_KWARGS) as demo:
    gr.Markdown(HEADER, elem_id="app-header")
    if config.LOW_MEMORY:
        gr.Markdown(
            f"**Low-RAM mode is on.** `{DEFAULT_MODEL}` is selected to keep this laptop responsive. "
            "Close unused browser tabs, and pick a bigger model under **Study settings** only if you have "
            "memory to spare.",
            elem_id="app-notice",
        )
    with gr.Tab("Chat"):
        chat_ui = gr.ChatInterface(
            fn=chat,
            chatbot=gr.Chatbot(
                show_label=False,
                layout="bubble",
                height=520,
                elem_id="scholar-chat",
                avatar_images=AVATARS,
                placeholder="Ask your first question, paste your homework, or start a quiz.",
            ),
            textbox=gr.Textbox(placeholder="Ask a question, paste homework, or start a quiz...", scale=8),
            additional_inputs=[
                gr.Dropdown(list(llm.MODES), value="Just chat", label="Study mode", render=False),
                gr.Dropdown(list(llm.LANGUAGES), value="English", label="Language", render=False),
                gr.Checkbox(value=False, label="Also search my notes (My notes tab)", render=False),
                gr.Dropdown(MODELS, value=DEFAULT_MODEL, label="Chat model", render=False),
            ],
            additional_inputs_accordion="Study settings",
            examples=[
                ["Explain photosynthesis like I am ten", "Explain simply", "English", False, DEFAULT_MODEL],
                ["Quiz me on Newton's laws", "Quiz me", "English", False, DEFAULT_MODEL],
                ["Summarise my notes on photosynthesis", "Summarize my text", "English", True, DEFAULT_MODEL],
            ],
            save_history=True,
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
    gr.Markdown(
        '<p><span class="dot"></span>Runs locally. Nothing leaves your laptop unless you save a web page.</p>',
        elem_id="app-footer",
    )

demo.queue(default_concurrency_limit=1, max_size=8)

if __name__ == "__main__":
    if config.LOW_MEMORY:
        print(f"Low memory detected: using {DEFAULT_MODEL} to keep the laptop responsive.")
        print("Set OS_MODEL to force another model, or OS_LOW_MEMORY=0 to disable this.")
    demo.launch(**LAUNCH_KWARGS)
