"""OfflineScholar web server: FastAPI API + the custom chat frontend."""
import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import config
import llm
import services
import store

WEB_DIR = config.BASE / "web"
logger = logging.getLogger("offlinescholar")


def _warm_up():
    """Index changed notes and preload the model so the first question is quick."""
    if config.AUTO_INDEX:
        try:
            message = services.scan_notes()
            logger.info("Notes ready: %s", message)
        except Exception as error:
            logger.warning("Could not index notes on startup: %s", error)
    if config.WARMUP:
        try:
            llm.warm_up()
        except Exception as error:
            logger.warning("Could not preload the chat model: %s", error)


@asynccontextmanager
async def lifespan(_app):
    if config.AUTO_INDEX or config.WARMUP:
        threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="OfflineScholar", docs_url=None, redoc_url=None, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    mode: str = "Just chat"
    language: str = "English"
    use_notes: bool = True
    use_web: bool = False
    model: Optional[str] = None


class RenameRequest(BaseModel):
    title: str


class UrlRequest(BaseModel):
    url: str


def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chat_models():
    return [m for m in llm.list_models() if "embed" not in m.lower()]


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.svg")
def favicon():
    return FileResponse(WEB_DIR / "favicon.svg")


@app.get("/api/status")
def status():
    models = _chat_models()
    return {
        "ollama": bool(models),
        "models": models or [config.CHAT_MODEL],
        "model": llm.default_model(models),
        "embed_model": config.EMBED_MODEL,
        "low_memory": config.LOW_MEMORY,
        "available_memory_gb": config.AVAILABLE_MEMORY_GB,
        "modes": list(llm.MODES),
        "languages": list(llm.LANGUAGES),
        "notes": services.notes_summary(),
    }


@app.get("/api/conversations")
def conversations():
    con = store.connect()
    try:
        return {"conversations": store.list_conversations(con)}
    finally:
        con.close()


@app.post("/api/conversations")
def new_conversation():
    con = store.connect()
    try:
        conversation_id = store.create_conversation(con, "New chat")
    finally:
        con.close()
    return {"id": conversation_id, "title": "New chat", "messages": []}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: int):
    con = store.connect()
    try:
        if not store.conversation_exists(con, conversation_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        row = con.execute("SELECT title FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        return {
            "id": conversation_id,
            "title": row[0],
            "messages": store.conversation_messages(con, conversation_id),
        }
    finally:
        con.close()


@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: int, request: RenameRequest):
    title = " ".join(request.title.split())[:80]
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    con = store.connect()
    try:
        if not store.conversation_exists(con, conversation_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        store.rename_conversation(con, conversation_id, title)
    finally:
        con.close()
    return {"id": conversation_id, "title": title}


@app.delete("/api/conversations/{conversation_id}")
def remove_conversation(conversation_id: int):
    con = store.connect()
    try:
        if not store.conversation_exists(con, conversation_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        store.delete_conversation(con, conversation_id)
    finally:
        con.close()
    return {"deleted": conversation_id}


@app.post("/api/chat")
def chat(request: ChatRequest):
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(message) > config.MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Message is too long (limit {config.MAX_MESSAGE_CHARS:,} characters).",
        )
    model = request.model or llm.default_model(_chat_models())

    con = store.connect()
    try:
        conversation_id = request.conversation_id
        if not conversation_id or not store.conversation_exists(con, conversation_id):
            conversation_id = store.create_conversation(con, services.title_for(message))
        history = store.conversation_messages(con, conversation_id, limit=config.HISTORY_LIMIT)
        store.append_message(con, conversation_id, "user", message)
    finally:
        con.close()

    def generate():
        yield _sse({"type": "start", "conversation_id": conversation_id})
        parts, failed = [], None
        passages = services.retrieve(message, request.use_notes)
        web_passages = []
        try:
            for token in services.answer_stream(history, message, request.mode, request.language,
                                                request.use_notes, model, passages=passages,
                                                use_web=config.LIVE_LOOKUP_ENABLED and request.use_web,
                                                web_sink=web_passages):
                parts.append(token)
                yield _sse({"type": "token", "text": token})
        except Exception as e:
            failed = services.friendly_error(e, model)
            parts.append(failed)
            yield _sse({"type": "error", "message": failed})
        finally:
            text = "" if failed else "".join(parts).strip()
            if text:
                writer = store.connect()
                try:
                    store.append_message(writer, conversation_id, "assistant", text)
                finally:
                    writer.close()
        evidence = web_passages or passages
        verification = services.verify_answer(text, evidence)
        verification["web_used"] = bool(web_passages)
        if web_passages:
            verification["notes_used"] = False
        if evidence and verification["citations"]:
            yield _sse({"type": "sources", "sources": services.sources_for(evidence)})
        yield _sse({"type": "done", "conversation_id": conversation_id, "verification": verification})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _notes_payload(message=None, saved=None):
    payload = {
        "files": services.library_files(),
        "summary": services.notes_summary(),
        "folder": str(config.LIBRARY_DIR),
    }
    if message:
        payload["message"] = message
    if saved is not None:
        payload["saved"] = bool(saved)
    return payload


@app.get("/api/notes")
def notes():
    return _notes_payload()


@app.post("/api/notes/upload")
async def upload_notes(files: list[UploadFile] = File(...)):
    payload = []
    for f in files:
        data = await f.read(services.MAX_UPLOAD_BYTES + 1)
        payload.append((f.filename, data))
    message, saved = await run_in_threadpool(services.add_uploads, payload)
    return _notes_payload(message, saved)


@app.post("/api/notes/url")
def add_note_url(request: UrlRequest):
    message = services.add_url(request.url)
    return _notes_payload(message)


@app.post("/api/notes/rescan")
def rescan_notes():
    message = services.scan_notes()
    return _notes_payload(message)


@app.post("/api/notes/clear")
def clear_notes():
    message = services.clear_notes_index()
    return _notes_payload(message)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("OS_PORT", "7860")), log_level="info")
