# OfflineScholar

OfflineScholar is a lightweight, offline‑first study assistant that runs entirely on your laptop. It indexes local documents (PDF, TXT, MD, DOCX) into a SQLite FTS5 database, lets you ask questions via a Gradio UI, and answers using a locally‑run Ollama model (e.g., Gemma). No cloud APIs, no API keys, and it works without an internet connection after the initial setup.

## Features
- **Library ingestion** – drop files into `library/` and click **Re‑scan Library** to index new/changed files.
- **BM25 search** – retrieves up to 4 relevant passages per query.
- **LLM answering** – prompts Ollama's Gemma model to answer *only* with the retrieved passages; falls back to a friendly “I couldn't find this in your library.”
- **Citations** – every answer ends with a list of source file names and sections.
- **Study modes** – Explain simply, Summarize, Quiz me, Make flashcards, Step‑by‑step solution.
- **Multi‑language** – English, Nigerian Pidgin, Hausa (technical terms stay English).
- **Save web page** – optional download‑and‑index of a URL (fails gracefully when offline).
- **History** – last 20 Q&A stored locally.
- **Offline badge** – indicates when the app is running without internet.

## Project structure
```
OfflineScholar/
├─ app.py               # Gradio UI
├─ config.py            # Settings & env vars
├─ ingest.py            # Document parsing & indexing
├─ search.py            # SQLite BM25 search
├─ llm.py               # Ollama wrapper
├─ requirements.txt     # Python deps
├─ README.md            # ← you are here
├─ .gitignore
├─ library/             # Sample documents (user adds more)
│   ├─ sample1.txt
│   └─ sample2.txt
└─ test_offline_scholar.py  # Simple test script
```

## Setup (Fedora) – step‑by‑step
```bash
# 1. Clone the repo (or copy the files into a folder)
mkdir -p ~/OfflineScholar && cd ~/OfflineScholar
# (Assuming the files have been created as per this conversation)

# 2. Create a virtual environment
python3.12 -m venv venv
source venv/bin/activate

# 3. Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Install Ollama (if not already installed)
# Follow https://ollama.com/download
# After installing, pull a Gemma model, e.g.:
ollama pull gemma4:e2b-it-qat   # default model
# or a smaller alternative:
ollama pull gemma3:1b

# 5. Start Ollama server (in a separate terminal)
ollama serve

# 6. Run the app (offline mode – Wi‑Fi can be off)
# Use the default model or override via env var:
# OS_MODEL=gemma3:1b python app.py
python app.py
```
Open the displayed URL (usually `http://127.0.0.1:7860`) in a browser.

## Running the test script
```bash
python test_offline_scholar.py
```
It will:
1. Index the two sample files.
2. Ask a question that exists in the library and print the answer with citations.
3. Ask a nonsense question and show the fallback response.

## Environment variables (optional)
- `OS_MODEL` – Ollama model name (default **gemma4:e2b-it-qat**).
- `USE_EMBEDDINGS` – set to `true` to enable embedding‑based search (requires an Ollama embedding model).
- `EMBEDDING_MODEL` – name of the embedding model (default **nomic-embed-text**).

## Troubleshooting
- **Ollama isn’t running** – the UI shows a clear error. Start it with `ollama serve`.
- **Empty library** – the app displays “*Library is empty.*” – add files to `library/` and click **Re‑scan Library**.
- **Corrupt PDF/DOCX** – ingestion logs the error and skips the file; the UI remains stable.
- **No internet** – all features work except the “Save Web Page” button, which shows a friendly message.

Enjoy studying offline!
