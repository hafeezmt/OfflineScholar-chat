# OfflineScholar

Chat with an AI for your studies **with no internet**, the way you would chat with ChatGPT or Claude. Ask questions, get homework explained, plan essays, practise quizzes. Everything runs on your own laptop.

## Why it exists

Students often need help with assignments and research exactly when data is expensive or the network is down. OfflineScholar moves the AI onto the laptop so it works anywhere, for free.

## Open-source AI used

- **Gemma 4** (`gemma4:e2b-it-qat`), Google's open-weight model, runs locally through **Ollama** and does the chatting.
- **Snowflake Arctic Embed** (`snowflake-arctic-embed:33m`), Snowflake's open-weight embedding model, also local through Ollama. It powers the optional "search my notes" feature.
- Gradio for the interface, SQLite for the notes index.

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
model any time under **Study settings** in the Chat tab.

Run (two terminal tabs):

```bash
# tab 1
ollama serve
# tab 2
source venv/bin/activate
python app.py
```

Open the link it prints (usually http://127.0.0.1:7860).

Prefer the terminal? The same library and models work without a browser:

```bash
python cli.py index                          # index new or changed notes
python cli.py list                           # show files and index state
python cli.py search "photosynthesis"        # find matching passages
python cli.py ask "explain Newton's second law" --mode "Explain simply"
```

## Features

- Normal chat that remembers the conversation
- Study modes: just chat, explain simply, homework helper, essay outline, quiz me, summarize my text
- Replies in English, Nigerian Pidgin or Hausa
- Optional notes: add .pdf, .docx, .txt, .md files or saved web pages, tick "Also search my notes", and the AI uses them and shows which file it used
- Notes list shows each file's size and whether it is indexed
- Clear the index without deleting your files, then re-scan
- Your chat history is kept in this browser: reopen an older conversation from the history panel, or start a new one
- Model picker, plus automatic low-RAM mode so the laptop stays responsive
- Example prompts for quick starts
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

## Check the notes search works

```bash
python test_core.py       # indexing and search with sample notes
python test_features.py   # chunking, uploads, history and page extraction
```

## Troubleshooting

- **"The model isn't installed"**: run `ollama pull gemma4:e2b-it-qat` (and `ollama pull snowflake-arctic-embed:33m` for notes search).
- **"I can't reach Ollama"**: start it with `ollama serve`.
- **Search misses your notes**: open My notes and press Re-scan library; if the file shows "not indexed", it could not be read (scanned PDFs have no text layer).
- **Wrong or stale answers from notes**: press "Clear index (keeps files)" and then Re-scan library.
- **The laptop freezes or hangs while answering**: a large model is being swapped in and out of memory. Use the `gemma3:1b` model in Study settings (or `OS_MODEL=gemma3:1b`), close unused browser tabs, and keep `OS_NUM_THREAD` low. On 8 GB machines avoid `gemma4:e2b-it-qat` while other apps are open.

## Low memory tip

On an 8 GB laptop, close browser tabs you don't need. OfflineScholar switches to the
small lite model automatically, but the first reply still takes a few seconds while the
model loads. If the desktop starts to stutter, lower `OS_NUM_THREAD` or use `python cli.py ask`
instead of the browser interface.
