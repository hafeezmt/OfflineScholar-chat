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
ollama pull gemma4:e2b-it-qat
ollama pull snowflake-arctic-embed:33m   # only needed for the notes feature
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run (two terminal tabs):

```bash
# tab 1
ollama serve
# tab 2
source venv/bin/activate
python app.py
```

Open the link it prints (usually http://127.0.0.1:7860).

## Features

- Normal chat that remembers the conversation
- Study modes: just chat, explain simply, homework helper, essay outline, quiz me, summarize my text
- Replies in English, Nigerian Pidgin or Hausa
- Optional notes: add .pdf, .docx, .txt, .md files or saved web pages, tick "Also search my notes", and the AI uses them and shows which file it used
- Friendly messages when Ollama is not running or the model is not installed

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `OS_MODEL` | `gemma4:e2b-it-qat` | Chat model. Any Ollama chat model works, for example `gemma3:1b` |
| `OS_EMBED` | `snowflake-arctic-embed:33m` | Notes search model |
| `OS_EMBEDDINGS` | `1` | Set to `0` for keyword-only notes search |

## Check the notes search works

```bash
python test_core.py
```

## Low memory tip

On an 8 GB laptop, close browser tabs you don't need. The first reply can take a minute while the model loads.
