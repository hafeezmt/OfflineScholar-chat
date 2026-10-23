"""Terminal front end: index your notes, search them, and chat without the web UI."""
import argparse
import sys
from pathlib import Path

from . import config, ingest, llm, search, services, store


def index_notes():
    con = store.connect()
    try:
        return ingest.scan_library(con, embed_fn=llm.embed if config.USE_EMBEDDINGS else None)
    finally:
        con.close()


def cmd_index(args):
    print(index_notes())
    return 0


def cmd_list(args):
    con = store.connect()
    try:
        rows = {row[0]: row[1] for row in con.execute("SELECT path, has_emb FROM files")}
    finally:
        con.close()
    files = ingest.library_files()
    if not files:
        print("No files in the library yet. Add .pdf, .docx, .txt or .md files to", config.LIBRARY_DIR)
        return 0
    for p in files:
        if str(p) not in rows:
            state = "not indexed"
        else:
            state = "indexed" if rows[str(p)] else "indexed (keyword only)"
        print(f"{p.name}  [{state}]")
    print(f"{len(files)} file(s).")
    return 0


def cmd_search(args):
    passages = search.find(args.query)
    if not passages:
        print("No matching notes. Try `python cli.py index` after adding files.")
        return 1
    for i, p in enumerate(passages, 1):
        print(f"[{i}] {Path(p['path']).name} ({p['label']})")
        print(p["text"], "\n")
    return 0


def cmd_ask(args):
    model = args.model or llm.default_model()
    passages = [] if args.no_notes else services.retrieve(args.message)
    try:
        for token in llm.chat_stream([], args.message, args.mode, args.language, passages, model=model):
            print(token, end="", flush=True)
    except Exception as e:
        err = str(e).lower()
        if "not found" in err:
            print(f"\nThe model is not installed. Run: ollama pull {model}")
        elif "connect" in err or "refused" in err:
            print("\nCannot reach Ollama. Start it with: ollama serve")
        else:
            print(f"\nSomething went wrong: {e}")
        return 1
    print()
    if passages:
        print("*From your notes:* " + ", ".join(
            f"[{i}] {Path(p['path']).name}" for i, p in enumerate(passages, 1)))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="cli.py", description="OfflineScholar from the terminal")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("index", help="index new or changed files in the library")
    sub.add_parser("list", help="list library files and their index state")

    p_search = sub.add_parser("search", help="search your notes")
    p_search.add_argument("query")

    p_ask = sub.add_parser("ask", help="ask the local model a question")
    p_ask.add_argument("message")
    p_ask.add_argument("--mode", default="Just chat", choices=list(llm.MODES))
    p_ask.add_argument("--language", default="English", choices=list(llm.LANGUAGES))
    p_ask.add_argument("--no-notes", action="store_true", help="do not search the library")
    p_ask.add_argument("--model", default=None,
                       help="Ollama chat model to use (default: the installed model)")

    args = parser.parse_args(argv)
    return {
        "index": cmd_index,
        "list": cmd_list,
        "search": cmd_search,
        "ask": cmd_ask,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
