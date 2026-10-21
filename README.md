# OfflineScholar

Chat with an AI for your studies **with no internet**, the way you would chat with ChatGPT or Claude. Ask questions, get homework explained, plan essays, practise quizzes. Everything runs on your own laptop.

## Why it exists

Students often need help with assignments and research exactly when data is expensive or the network is down. OfflineScholar moves the AI onto the laptop so it works anywhere, for free.

## Open-source AI used

- **Gemma 4** (`gemma4:e2b-it-qat`), Google's open-weight model, runs locally through **Ollama** and does the chatting.
- **Snowflake Arctic Embed** (`snowflake-arctic-embed:33m`), Snowflake's open-weight embedding model, also local through Ollama. It powers the optional "search my notes" feature.
- A small FastAPI server with a hand-written offline web interface (no CDN, no cloud), plus SQLite for chats and the notes index.
- The original Gradio interface is still included as `gradio_app.py` if you prefer it.

Nothing leaves the laptop. The only network use is the optional "Save a web page" button.

## Setup (Fedora / Linux)

```bash
ollama pull gemma4:e2b-it-qat            # best answers, needs about 5 GB of free RAM
ollama pull gemma3:1b                    # lite model for 8 GB laptops (used automatically)
ollama pull snowflake-arctic-embed:33m   # only needed for the notes feature
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On a machine with less than about 5.5 GB of available RAM, OfflineScholar starts in
**low-RAM mode** and uses `gemma3:1b` instead of the larger model. You can change the
model any time from the model picker above the message box.

Run:

```bash
source venv/bin/activate
python app.py
```

Open http://127.0.0.1:7860. Ollama is usually already running as a service; if it is not,
start it in another terminal with `ollama serve`. For an app-style window without browser
tabs, run `./launch.sh` — it starts the local service first if needed. The original Gradio
interface is still available with `python gradio_app.py`.

### Run in the background (optional)

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/offlinescholar.service <<'EOF'
[Unit]
Description=OfflineScholar local study assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=%h/offlinescholar
ExecStart=%h/offlinescholar/venv/bin/python %h/offlinescholar/app.py
Environment=OS_PORT=7860
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now offlinescholar
```

Check it with `systemctl --user status offlinescholar` or open http://127.0.0.1:7860.

Prefer the terminal? The same library and models work without a browser:

```bash
python cli.py index                          # index new or changed notes
python cli.py list                           # show files and index state
python cli.py search "photosynthesis"        # find matching passages
python cli.py ask "explain Newton's second law" --mode "Explain simply"
```

## Features

- Normal chat that remembers the conversation, with streaming replies
- Study modes: just chat, explain simply, homework helper, essay outline, quiz me, summarize my text
- Replies in English, Nigerian Pidgin or Hausa
- Optional notes: add .pdf, .docx, .txt, .md files or saved web pages, switch on "Use notes", and the AI uses them and cites passage numbers
- Notes library drawer with each file's size and index state, plus re-scan and clear
- Conversation history in a sidebar: search, rename or delete chats, and reopen them later
- Model picker, plus automatic low-RAM mode so the laptop stays responsive
- Light and dark themes, a mobile layout, and example prompts for quick starts
- Friendly messages when Ollama is not running or the model is not installed

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `OS_MODEL` | `gemma4:e2b-it-qat` | Chat model. Low-RAM machines default to `gemma3:1b`; set this to force one |
| `OS_EMBED` | `snowflake-arctic-embed:33m` | Notes search model |
| `OS_EMBEDDINGS` | `1` | Set to `0`/`off` for keyword-only notes search |
| `OS_TOP_K` | `4` | How many note passages to give the model |
| `OS_NUM_CTX` | `2048` | Context window for the chat model |
| `OS_TEMPERATURE` | `0.5` | Answer randomness, between 0 and 2 |
| `OS_HISTORY` | `8` | Messages kept from the conversation |
| `OS_CHUNK_WORDS` | `250` | Words per indexed chunk |
| `OS_CHUNK_OVERLAP` | `40` | Words shared by neighbouring chunks |
| `OS_LOW_MEMORY` | auto | `1` forces low-RAM mode, `0` turns it off |
| `OS_NUM_PREDICT` | `384` | Maximum tokens in one answer (lower is lighter) |
| `OS_NUM_THREAD` | half the CPUs | CPU threads used by the model; lower keeps the desktop responsive |
| `OS_NUM_BATCH` | `128` | Prompt batch size (lower uses less peak memory) |
| `OS_KEEP_ALIVE` | `2m` | How long the model stays in memory after the last answer |
| `OS_HOST` | `127.0.0.1` | Address the web app listens on (keep it local unless you know what you are doing) |
| `OS_PORT` | `7860` | Port for the web app |

## Check the notes search works

```bash
python test_core.py                         # indexing and search with sample notes
python -m unittest test_features test_server  # chunking, uploads, history, API and chat streaming
```

## Troubleshooting

- **"The model isn't installed"**: run `ollama pull gemma4:e2b-it-qat` (and `ollama pull snowflake-arctic-embed:33m` for notes search).
- **"I can't reach Ollama"**: start it with `ollama serve`.
- **Search misses your notes**: open Notes and press Re-scan; if the file shows "Not indexed", it could not be read (scanned PDFs have no text layer).
- **Wrong or stale answers from notes**: press Clear index (your files stay) and then Re-scan.
- **The laptop freezes or hangs while answering**: a large model is being swapped in and out of memory. Pick `gemma3:1b` in the model selector (or set `OS_MODEL=gemma3:1b`), close unused browser tabs, and keep `OS_NUM_THREAD` low. On 8 GB machines avoid `gemma4:e2b-it-qat` while other apps are open.

## Low memory tip

On an 8 GB laptop, close browser tabs you don't need. OfflineScholar switches to the
small lite model automatically, but the first reply still takes a few seconds while the
model loads. If the desktop starts to stutter, lower `OS_NUM_THREAD` or use `python cli.py ask`
instead of the browser interface.
