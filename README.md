# OfflineScholar

Chat with an AI for your studies **with no internet**, the way you would chat with ChatGPT or Claude. Ask questions, get homework explained, plan essays, practise quizzes. Everything runs on your own laptop.

## Why it exists

Students often need help with assignments and research exactly when data is expensive or the network is down. OfflineScholar moves the AI onto the laptop so it works anywhere, for free.

## Open-source AI used

- **Gemma 3 1B** (`gemma3:1b`) or **Qwen 2.5 1.5B** (`qwen2.5:1.5b`) runs locally through **Ollama** on 8 GB laptops; **Gemma 4** (`gemma4:e2b-it-qat`) gives the strongest answers when more RAM is free.
- **Snowflake Arctic Embed** (`snowflake-arctic-embed:33m`), Snowflake's open-weight embedding model, also local through Ollama. It powers the optional "search my notes" feature.
- A small FastAPI server with a hand-written offline web interface (no CDN, no cloud), plus SQLite for chats and the notes index.
- The original Gradio interface is still included as `gradio_app.py` if you prefer it.

Nothing leaves the laptop. The only network feature is the optional "Save a web page" button; the app itself answers offline.

## Setup (Fedora / Linux)

```bash
ollama pull gemma3:1b                    # small model for 8 GB laptops
ollama pull qwen2.5:1.5b                 # optional: better reasoning, still under 1 GB
ollama pull gemma4:e2b-it-qat            # best answers, needs about 5 GB of free RAM
ollama pull snowflake-arctic-embed:33m   # only needed for the notes feature
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On a machine with less than about 5.5 GB of available RAM, OfflineScholar starts in
**low-RAM mode** and uses `qwen2.5:1.5b` when it is installed, otherwise `gemma3:1b`.
You can change the model any time from the model picker above the message box. Note that
the first reply after a restart is slower while Ollama loads the model; the service
preloads it in the background.

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
- Grounded notes answers: add .pdf, .docx, .txt, .md files or saved web pages, switch on "Use notes", and relevant passages are quoted with `[1]` citations; unrelated notes are rejected instead of being forced into every answer
- Honest limits: if the notes do not cover a question, the app says so; current or time-sensitive questions such as "latest version" are refused offline instead of guessed
- Notes library drawer with each file's size and index state, plus re-scan and clear
- Conversation history in a sidebar: search, rename or delete chats, and reopen them later
- Model picker, plus automatic low-RAM mode so the laptop stays responsive
- Light and dark themes, a mobile layout, and example prompts for quick starts
- Friendly messages when Ollama is not running or the model is not installed
- Background indexing and model preloading on startup, so the first question is ready sooner

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `OS_MODEL` | `gemma4:e2b-it-qat` | Chat model. Low-RAM machines default to `gemma3:1b`; set this to force one |
| `OS_EMBED` | `snowflake-arctic-embed:33m` | Notes search model |
| `OS_EMBEDDINGS` | `1` | Set to `0`/`off` for keyword-only notes search |
| `OS_TOP_K` | `4` | Candidate passages retrieved before relevance filtering |
| `OS_RAG_MAX_PASSAGES` | `1` | Passages actually given to the model (lower is faster) |
| `OS_RAG_MIN_SCORE` | `0.62` | Minimum similarity for a semantic note match |
| `OS_RAG_MIN_MARGIN` | `0.06` | Drop weaker matches too far below the best one |
| `OS_RAG_PASSAGE_WORDS` | `90` | Maximum note words placed in the prompt |
| `OS_EXTRACTIVE_RAG` | `1` | Quote notes directly with a citation instead of asking the model to repeat them |
| `OS_NUM_CTX` | `2048` | Context window for the chat model |
| `OS_TEMPERATURE` | `0.2` | Answer randomness, between 0 and 2 |
| `OS_HISTORY` | `8` | Messages kept from the conversation |
| `OS_CHUNK_WORDS` | `160` | Words per indexed chunk |
| `OS_CHUNK_OVERLAP` | `30` | Words shared by neighbouring chunks |
| `OS_LOW_MEMORY` | auto | `1` forces low-RAM mode, `0` turns it off |
| `OS_NUM_PREDICT` | `384` | Maximum tokens in one answer (lower is lighter) |
| `OS_NUM_THREAD` | half the CPUs | CPU threads used by the model; lower keeps the desktop responsive |
| `OS_NUM_BATCH` | `128` | Prompt batch size (lower uses less peak memory) |
| `OS_KEEP_ALIVE` | `30m` | How long the model stays in memory after the last answer |
| `OS_AUTO_INDEX` | `1` | Re-index changed notes in the background at startup |
| `OS_WARMUP` | `1` | Preload the chat model at startup |
| `OS_HOST` | `127.0.0.1` | Address the web app listens on (keep it local unless you know what you are doing) |
| `OS_PORT` | `7860` | Port for the web app |

## How notes answers stay grounded

1. The question is matched against paragraph-sized note chunks. Weak or unrelated matches are dropped.
2. If the best passage contains the question's key terms, its answer sentences are quoted directly with a `[1]` citation. This is instant and cannot be hallucinated.
3. If the notes do not contain the answer, the app replies "Your notes do not cover that" instead of guessing.
4. "Latest/current" questions are refused instead of guessed; known false premises such as "Newton's fourth law" are corrected.
5. General questions still use the local chat model with a short prompt and no notes.

Set `OS_EXTRACTIVE_RAG=0` to always let the model write the answer from notes (slower, and small models may forget citations).

## Check quality and speed

```bash
python test_core.py                              # indexing and search with sample notes
python -m unittest test_features test_server test_rag  # API, chunking, retrieval and safety checks
python eval_quality.py --models gemma3:1b qwen2.5:1.5b --verbose
```

`eval_quality.py` runs real questions through Ollama and checks citations, refusal behaviour,
notes coverage, false premises and time-sensitive answers. It exits non-zero on failure, so it
can be used before a release.

## Troubleshooting

- **"The model isn't installed"**: run `ollama pull gemma4:e2b-it-qat` (and `ollama pull snowflake-arctic-embed:33m` for notes search).
- **"I can't reach Ollama"**: start it with `ollama serve`.
- **Search misses your notes**: open Notes and press Re-scan; if the file shows "Not indexed", it could not be read (scanned PDFs have no text layer).
- **Wrong or stale answers from notes**: press Clear index (your files stay) and then Re-scan. Note answers are quoted directly, so check the passage label shown under the reply.
- **The laptop freezes or hangs while answering**: a large model is being swapped in and out of memory. Pick `gemma3:1b` in the model selector (or set `OS_MODEL=gemma3:1b`), close unused browser tabs, and keep `OS_NUM_THREAD` low. On 8 GB machines avoid `gemma4:e2b-it-qat` while other apps are open.

## Low memory tip

On an 8 GB laptop, close browser tabs you don't need. OfflineScholar switches to the
small lite model automatically, but the first reply still takes a few seconds while the
model loads. If the desktop starts to stutter, lower `OS_NUM_THREAD` or use `python cli.py ask`
instead of the browser interface.
