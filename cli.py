"""Terminal front end: index your notes, search them, and chat without the web UI."""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import config
import ingest
import llm
import manage
import search
import services
import store


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


def cmd_chats(args):
    con = store.connect()
    try:
        conversations = store.list_conversations(con, limit=args.limit)
    finally:
        con.close()
    if getattr(args, "json", False):
        print(json.dumps(conversations, indent=2))
        return 0
    if not conversations:
        print("No saved chats yet. Ask a question to start one.")
        return 0
    for conversation in conversations:
        updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(conversation["updated"]))
        print(f'{conversation["id"]:>4}  {updated}  {conversation["title"]}')
    print(f"{len(conversations)} chat(s).")
    return 0


def cmd_delete(args):
    con = store.connect()
    try:
        if not store.conversation_exists(con, args.conversation_id):
            print(f"Chat {args.conversation_id} was not found.")
            return 1
        store.delete_conversation(con, args.conversation_id)
    finally:
        con.close()
    print(f"Deleted chat {args.conversation_id}.")
    return 0


def cmd_export(args):
    con = store.connect()
    try:
        markdown = store.conversation_markdown(con, args.conversation_id)
    finally:
        con.close()
    if markdown is None:
        print(f"Chat {args.conversation_id} was not found.")
        return 1
    if args.output:
        try:
            Path(args.output).write_text(markdown, encoding="utf-8")
        except OSError as e:
            print(f"Could not write {args.output}: {e}")
            return 1
        print(f"Exported chat {args.conversation_id} to {args.output}.")
    else:
        print(markdown, end="")
    return 0


def _chat_slug(title, fallback):
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:50]
    return slug or fallback


def cmd_export_all(args):
    con = store.connect()
    try:
        conversations = store.list_conversations(con, limit=1000)
        items = [(conversation, store.conversation_markdown(con, conversation["id"]))
                 for conversation in conversations]
    finally:
        con.close()
    if not items:
        print("No saved chats to export.")
        return 0
    folder = Path(args.folder)
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Could not create {folder}: {e}")
        return 1
    written = 0
    for conversation, markdown in items:
        if markdown is None:
            continue
        name = f'{conversation["id"]}-{_chat_slug(conversation["title"], "chat")}.md'
        try:
            (folder / name).write_text(markdown, encoding="utf-8")
        except OSError as e:
            print(f"Could not write {name}: {e}")
            return 1
        written += 1
    print(f"Exported {written} chat(s) to {folder}.")
    return 0


def cmd_config(args):
    settings = manage.load_settings()
    print(f"library: {config.LIBRARY_DIR}")
    print(f"database: {config.DB_PATH}")
    print(f"chat model: {settings['chat_model']}")
    print(f"embed model: {settings['embed_model']}")
    print(f"port: {settings['port']}")
    print(f"low memory: {'yes' if config.LOW_MEMORY else 'no'}")
    return 0


def cmd_search(args):
    passages = search.find(args.query, limit=args.limit)
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

    p_chats = sub.add_parser("chats", help="list saved chats")
    p_chats.add_argument("--limit", type=int, default=20, help="maximum chats to show")
    p_chats.add_argument("--json", action="store_true", help="print JSON for scripts")

    p_delete = sub.add_parser("delete", help="delete a saved chat")
    p_delete.add_argument("conversation_id", type=int, help="chat number shown by the chats command")

    p_export = sub.add_parser("export", help="export a saved chat as Markdown")
    p_export.add_argument("conversation_id", type=int, help="chat number shown by the chats command")
    p_export.add_argument("-o", "--output", default=None, help="write to a file instead of printing")

    p_export_all = sub.add_parser("export-all", help="export every saved chat as Markdown")
    p_export_all.add_argument("folder", help="folder to write the Markdown files into")

    sub.add_parser("config", help="show the effective paths, models and port")

    p_search = sub.add_parser("search", help="search your notes")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=config.TOP_K,
                          help="maximum passages to show")

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
        "chats": cmd_chats,
        "delete": cmd_delete,
        "export": cmd_export,
        "export-all": cmd_export_all,
        "config": cmd_config,
        "search": cmd_search,
        "ask": cmd_ask,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
