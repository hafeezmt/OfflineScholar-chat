# OfflineScholar

Chat with an AI for your studies **with no internet**, the way you would chat with ChatGPT or Claude. Ask questions, get homework explained, plan essays, practise quizzes. Everything runs on your own laptop.

## Why it exists

Students often need help with assignments and research exactly when data is expensive or the network is down. OfflineScholar moves the AI onto the laptop so it works anywhere, for free.

## Open-source AI used

- **Gemma 3 1B** (`gemma3:1b`) or **Qwen 2.5 1.5B** (`qwen2.5:1.5b`) runs locally through **Ollama** on 8 GB laptops; **Gemma 4** (`gemma4:e2b-it-qat`) gives the strongest answers when more RAM is free.
- **Snowflake Arctic Embed** (`snowflake-arctic-embed:33m`), Snowflake's open-weight embedding model, also local through Ollama. It powers the optional "search my notes" feature.
- A small FastAPI server with a hand-written offline web interface (no CDN, no cloud), plus SQLite for chats and the notes index.
- The original Gradio interface is optional; see `gradio_app.py` if you prefer it.

Nothing leaves the laptop. The only network feature is the optional "Save a web page" button; the app itself answers offline.

## Install with one command

Windows 10/11, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/hafeezmt/OfflineScholar-chat/main/install.ps1 | iex"
```

Linux/macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/hafeezmt/OfflineScholar-chat/main/install.sh | bash
```

The installer downloads the app into `~/OfflineScholar`, installs Ollama and Python if they
are missing, asks which chat model(s) you want, checks your free disk and RAM, and installs
the `offlinescholar` command and desktop app. It uses only the lightweight web dependencies
(the old Gradio interface is skipped), so setup is faster. The first run needs internet;
the space depends on the models you choose (about 2 GB for Gemma 3 1B, up to roughly 6 GB
with Gemma 4). After that the app works offline.

The installer **does not leave OfflineScholar running**. Start it when you want it, then stop
it when you are done:

```bash
offlinescholar up
offlinescholar stop
```

If `offlinescholar` is not found immediately after installing, open a new terminal. The
command is installed in `~/.local/bin` on Linux/macOS and on your user `PATH` on Windows.

To choose another folder or port:

```bash
curl -fsSL https://raw.githubusercontent.com/hafeezmt/OfflineScholar-chat/main/install.sh | OS_INSTALL_DIR="$HOME/apps/OfflineScholar" OS_PORT=7861 bash
```

On Windows, set the same variables before running the PowerShell command:

```powershell
$env:OS_INSTALL_DIR = "D:\OfflineScholar"
$env:OS_PORT = "7861"
$env:OS_MODELS = "gemma3:1b qwen2.5:1.5b"
irm https://raw.githubusercontent.com/hafeezmt/OfflineScholar-chat/main/install.ps1 | iex
```

### Choose your models

After updating the app code, the installer shows a model menu with download sizes and your
free disk/RAM:

| Model | Download | Best for |
|---|---|---|
| `gemma3:1b` (Gemma 3 1B) | 806 MB | Default for 8 GB laptops; fastest |
| `qwen2.5:1.5b` (Qwen 2.5 1.5B) | 986 MB | Better reasoning, still light |
| `gemma4:e2b-it-qat` (Gemma 4 E2B QAT) | 4.3 GB | Best answers, needs more free RAM |

Enter one or more numbers, for example `1 2`. Press Enter for the default (Gemma 3 1B).
Nothing is downloaded until you confirm. The 67 MB Snowflake notes-search model is always
installed. If disk space is short, or Gemma 4 is selected on a low-RAM machine, the
installer warns you and asks before continuing. You can free space or choose a smaller
model instead.

For scripted installs, choose models without the menu:

```bash
curl -fsSL https://raw.githubusercontent.com/hafeezmt/OfflineScholar-chat/main/install.sh | OS_MODELS="gemma3:1b qwen2.5:1.5b" bash
```

`OS_CHAT_MODEL` still selects a single model. If no terminal is available and neither
variable is set, the installer stops rather than downloading without consent.

For a headless or scripted install, set `OS_SKIP_DESKTOP=1` to skip the desktop app.
`OS_SKIP_MODELS=1` skips all model downloads when they are already installed, and
`OS_SKIP_DEPS=1` skips system package installation.

## Start, stop and release RAM

OfflineScholar is on-demand. There is no always-on background service.

| Command | What it does |
|---|---|
| `offlinescholar up` | Starts the local server, waits until it is ready, prints the URL and opens your browser |
| `offlinescholar start` | Same as `up` |
| `offlinescholar stop` | Stops the server and unloads the chat and notes models from Ollama |
| `offlinescholar down` | Same as `stop` |
| `offlinescholar restart` | Stops, unloads the models, then starts again |
| `offlinescholar status` | Shows whether it is running and which model is active |
| `offlinescholar up --no-open` | Starts it without opening a browser |

Typical session:

```text
$ offlinescholar up
OfflineScholar is running at http://127.0.0.1:7860
Stop it with: offlinescholar stop

$ offlinescholar status
OfflineScholar is running at http://127.0.0.1:7860
Model: gemma3:1b
Stop it with: offlinescholar stop

$ offlinescholar stop
OfflineScholar stopped and models unloaded.
```

The `stop` command does two things:

1. Stops the OfflineScholar web server.
2. Runs `ollama stop` for the chat model and the notes search model, releasing their RAM
   immediately instead of waiting for Ollama's keep-alive timer.

Ollama itself stays installed and may remain running as a small background service. Other
apps that use Ollama are not stopped. You can confirm that OfflineScholar's models are gone
with `ollama ps`.

`down` is provided as a shorter alias for `stop`. An `offlinescolar` alias is also installed
for convenience, but `offlinescholar` is the normal spelling.

### Change the port for one session

```bash
OS_PORT=7861 offlinescholar up
```

The desktop app uses the port saved during installation (normally `7860`). To change the
desktop app's port permanently, rerun the installer with `OS_PORT=7861`.

## Desktop app

The installer also installs a small desktop app for people who do not want to use a terminal.

- **Windows**: open **OfflineScholar** from the Start Menu or Desktop shortcut.
- **Linux**: open **OfflineScholar** from your applications menu.
- **macOS**: open **OfflineScholar** from `~/Applications/OfflineScholar.app` or Launchpad.

The app starts the server automatically, shows the local URL, and opens it in your browser.
**Closing the OfflineScholar window stops the server and unloads the models.** If the app is
already running, opening it again simply shows the running URL.

The desktop app needs Tk, which is included with the standard Python installer on Windows and
macOS. On Linux the installer adds the appropriate system package when needed. If the
desktop app is unavailable, the `offlinescholar` command still works.

You can also launch the desktop window from a terminal:

```bash
./launch.sh
```

## Manual setup (Linux/macOS)

Use this only if you do not want the one-command installer.

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
You can change the model any time from the model picker above the message box. The first
reply after a start is slower while Ollama loads the model; the service preloads it in the
background.

Start and stop it with the manager instead of leaving a server running:

```bash
source venv/bin/activate
python manage.py up
python manage.py stop
```

Open http://127.0.0.1:7860. Ollama is usually already running as a service; if it is not,
start it in another terminal with `ollama serve`. For the desktop window, run
`./launch.sh`. The original Gradio interface is optional: install it with
`pip install -r requirements-gradio.txt`, then run `python gradio_app.py`.

To make the short command available after a manual install, link the included wrapper
somewhere on your `PATH`:

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/offlinescholar" ~/.local/bin/offlinescholar
```

## Settings

Settings are read from environment variables and from `settings.json` in the app folder.
The installer writes `settings.json` with the model and port you chose. Environment variables
win over the file.

| Variable | Default | Meaning |
|---|---|---|
| `OS_MODEL` | first model selected during install | Chat model. Low-RAM machines normally use `gemma3:1b`; set this to force one |
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
| `OS_KEEP_ALIVE` | `30m` | How long the model stays loaded while the app is running; `stop` unloads it immediately |
| `OS_AUTO_INDEX` | `1` | Re-index changed notes in the background at startup |
| `OS_WARMUP` | `1` | Preload the chat model at startup |
| `OS_HOST` | `127.0.0.1` | Address the web app listens on (keep it local unless you know what you are doing) |
| `OS_PORT` | `7860` | Port for the web app |
| `OS_SKIP_DESKTOP` | `0` | Set to `1` during installation to skip the desktop app |

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

## How notes answers stay grounded

1. The question is matched against paragraph-sized note chunks. Weak or unrelated matches are dropped.
2. If the best passage contains the question's key terms, its answer sentences are quoted directly with a `[1]` citation. This is instant and cannot be hallucinated.
3. If the notes do not contain the answer, the app replies "Your notes do not cover that" instead of guessing.
4. "Latest/current" questions are refused instead of guessed; known false premises such as "Newton's fourth law" are corrected.
5. General questions still use the local chat model with a short prompt and no notes.

Set `OS_EXTRACTIVE_RAG=0` to always let the model write the answer from notes (slower, and small models may forget citations).

## Terminal tools

The browser is optional. The same library and models work from the terminal:

```bash
python cli.py index                          # index new or changed notes
python cli.py list                           # show files and index state
python cli.py search "photosynthesis"        # find matching passages
python cli.py ask "explain Newton's second law" --mode "Explain simply"
```

## Check quality and speed

```bash
python test_core.py                              # indexing and search with sample notes
python -m unittest test_features test_server test_rag test_manage  # API, chunking, retrieval, safety and start/stop checks
python eval_quality.py --models gemma3:1b qwen2.5:1.5b --verbose
```

`eval_quality.py` runs real questions through Ollama and checks citations, refusal behaviour,
notes coverage, false premises and time-sensitive answers. It exits non-zero on failure, so it
can be used before a release.

## Troubleshooting

### `offlinescholar: command not found`

- Open a new terminal first; the installer may have just added `~/.local/bin` to your shell
  startup file.
- Run the full path: `~/.local/bin/offlinescholar up` (Linux/macOS).
- Add `~/.local/bin` to your `PATH` if your shell does not already include it.
- On Windows, open a new PowerShell window. If the command is still missing, run
  `%USERPROFILE%\OfflineScholar\offlinescholar.cmd up`, or check that the OfflineScholar
  folder is in your user `PATH`.

### The server will not start

Run `offlinescholar status` and check `~/OfflineScholar/server.log`. Common causes are an
unreachable Ollama service or a port already in use. Start Ollama with `ollama serve`, or try
another port with `OS_PORT=7861 offlinescholar up`.

### `ollama ps` still shows models

Run `offlinescholar stop`. It explicitly unloads the chat and embedding models. If you started
the app manually with `python app.py`, stop that process first, then run
`ollama stop gemma3:1b` and `ollama stop snowflake-arctic-embed:33m`.

### The desktop app does not open

The desktop app needs Tk support for Python. On Linux install `python3-tkinter` (Fedora),
`python3-tk` (Debian/Ubuntu) or `tk` (Arch), then rerun the installer. On macOS, install
`python-tk` with Homebrew if your Python does not include it. The command-line version does
not need Tk and will continue to work.

### The app is slow on the first question

The model is being loaded into RAM. After that it stays warm while the app is running. Use
`gemma3:1b` on low-RAM machines, close unused browser tabs, and run `offlinescholar stop` when
you are finished to release the model memory.

## Low memory tip

On an 8 GB laptop, close browser tabs you don't need. OfflineScholar switches to the
small lite model automatically, but the first reply after `offlinescholar up` still takes a
few seconds while the model loads. If the desktop starts to stutter, lower `OS_NUM_THREAD` or
use `python cli.py ask` instead of the browser interface.
