# app.py
"""Main Gradio application for OfflineScholar.
Features:
- Library management (list, upload, re‑scan)
- Ask questions with study mode & language selection
- Save web page for offline use
- History of last 20 Q&A stored locally
- Offline status badge
- Custom CSS support
"""
import os
import shutil
import json
import threading
import requests
from pathlib import Path
import gradio as gr

# ------------------------------------------------------------
# Load custom CSS (if the file exists)
# ------------------------------------------------------------
CUSTOM_CSS_PATH = Path(__file__).parent / "static" / "custom.css"
if CUSTOM_CSS_PATH.is_file():
    with open(CUSTOM_CSS_PATH, "r", encoding="utf-8") as f:
        CUSTOM_CSS = f.read()
else:
    CUSTOM_CSS = ""

# ------------------------------------------------------------
# Project imports
# ------------------------------------------------------------
from config import LIBRARY_PATH, DB_PATH
from ingest import scan_library, ingest_file, get_connection
from search import bm25_search
from llm import generate_answer

# ------------------------------------------------------------
# Constants & helpers
# ------------------------------------------------------------
HISTORY_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "history.json"))
MAX_HISTORY = 20

# Ensure library folder exists
os.makedirs(LIBRARY_PATH, exist_ok=True)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Failed to save history: {e}")

def update_history(question, answer):
    hist = load_history()
    hist.append({"question": question, "answer": answer})
    hist = hist[-MAX_HISTORY:]
    save_history(hist)
    return hist

def format_history():
    hist = load_history()
    if not hist:
        return "*No history yet.*"
    md = "## History (last 20)\n"
    for i, entry in enumerate(reversed(hist), 1):
        md += f"**Q{i}:** {entry['question']}\n\n**A{i}:** {entry['answer']}\n\n---\n"
    return md

def list_library_files():
    files = []
    for p in Path(LIBRARY_PATH).rglob("*.*"):
        if p.is_file():
            rel = p.relative_to(LIBRARY_PATH)
            files.append(str(rel))
    if not files:
        return "*Library is empty.*"
    return "\n".join(f"- {f}" for f in sorted(files))

def check_internet():
    try:
        requests.head("http://example.com", timeout=2)
        return True
    except Exception:
        return False

def save_page(url):
    if not check_internet():
        return "Internet is not available. Cannot download the page."
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        clean = soup.get_text(separator="\n")
        save_dir = Path(LIBRARY_PATH) / "saved_pages"
        os.makedirs(save_dir, exist_ok=True)
        filename = url.replace("://", "_").replace("/", "_")[:200] + ".txt"
        file_path = save_dir / filename
        file_path.write_text(clean, encoding="utf-8")
        ingest_file(get_connection(), file_path)
        return f"Page saved to {file_path.relative_to(Path(__file__).parent)} and indexed."
    except Exception as e:
        return f"Failed to download or save page: {e}"

def answer_question(question, mode, language):
    passages = bm25_search(question, top_k=4)
    if not passages:
        answer = "I couldn't find this in your library."
    else:
        answer = generate_answer(question, passages, mode, language)
    update_history(question, answer)
    return answer

def upload_file(file_path):
    if not file_path:
        return "No file uploaded."
    src = Path(file_path)
    dest = Path(LIBRARY_PATH) / src.name
    try:
        shutil.move(str(src), str(dest))
    except Exception as e:
        return f"Failed to move uploaded file: {e}"
    ingest_file(get_connection(), dest)
    return f"Uploaded and indexed {dest.name}."

def rescan_library():
    threading.Thread(target=scan_library, daemon=True).start()
    return "Rescanning library in background..."

# ------------------------------------------------------------
# UI definition (using Tabs for a clean, mobile‑friendly layout)
# ------------------------------------------------------------
with gr.Blocks() as demo:
    # Offline status badge at the top
    offline_badge = "✅ Offline mode: OK" if not check_internet() else "⚠️ Internet detected (only for Save page)"
    gr.Markdown(f"# OfflineScholar – Offline Study Assistant\n**{offline_badge}**")

    with gr.Tabs():
        # Ask tab
        with gr.TabItem("Ask"):
            gr.Markdown("## Ask a Question")
            question_input = gr.Textbox(label="Question", lines=2)
            mode_dropdown = gr.Dropdown(
                choices=["Default", "Explain simply", "Summarize", "Quiz me", "Make flashcards", "Step-by-step solution"],
                value="Default",
                label="Study mode",
            )
            language_dropdown = gr.Dropdown(
                choices=["English", "Nigerian Pidgin", "Hausa"],
                value="English",
                label="Answer language",
            )
            ask_btn = gr.Button("Ask")
            answer_output = gr.Markdown(label="Answer")
            ask_btn.click(fn=answer_question, inputs=[question_input, mode_dropdown, language_dropdown], outputs=answer_output)

        # Library tab
        with gr.TabItem("Library"):
            gr.Markdown("## Library Management")
            lib_md = gr.Markdown(value=list_library_files())
            upload = gr.File(label="Upload file (.txt, .md, .pdf, .docx)", file_types=[".txt", ".md", ".pdf", ".docx"])
            upload_btn = gr.Button("Upload")
            upload_btn.click(fn=upload_file, inputs=upload, outputs=lib_md)
            rescan_btn = gr.Button("Re‑scan Library")
            rescan_btn.click(fn=rescan_library, outputs=lib_md)

        # Save Page tab
        with gr.TabItem("Save Page"):
            gr.Markdown("## Save Web Page for Offline Use")
            url_input = gr.Textbox(label="URL", placeholder="https://example.com/article")
            save_btn = gr.Button("Save Page")
            save_output = gr.Markdown()
            save_btn.click(fn=save_page, inputs=url_input, outputs=save_output)

        # History tab
        with gr.TabItem("History"):
            gr.Markdown("## Interaction History")
            history_md = gr.Markdown(value=format_history())
            # Refresh history after each interaction
            ask_btn.click(fn=format_history, inputs=None, outputs=history_md)
            upload_btn.click(fn=format_history, inputs=None, outputs=history_md)
            rescan_btn.click(fn=format_history, inputs=None, outputs=history_md)

# ------------------------------------------------------------
# Launch the app – pass custom CSS (if any)
# ------------------------------------------------------------
demo.launch(theme=gr.themes.Default(primary_hue="green"), css=CUSTOM_CSS)
