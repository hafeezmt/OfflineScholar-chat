"""API checks for the FastAPI app. No Ollama or internet needed."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import config
import server
import store


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.db"
        self.patch = mock.patch.object(config, "DB_PATH", self.db)
        self.patch.start()
        self.client = TestClient(server.app)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_frontend_files_are_served(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("OfflineScholar", page.text)
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)
        self.assertEqual(self.client.get("/static/custom.css").status_code, 200)
        self.assertEqual(self.client.get("/favicon.svg").status_code, 200)

    def test_health_endpoint_is_available_without_ollama(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_status_reports_models_and_modes(self):
        with mock.patch.object(server.llm, "list_models", return_value=["gemma3:1b"]), \
                mock.patch.object(server.services, "notes_summary", return_value={"files": 0, "indexed": 0, "size": 0}):
            data = self.client.get("/api/status").json()
        self.assertTrue(data["ollama"])
        self.assertIn("gemma3:1b", data["models"])
        self.assertIn("Quiz me", data["modes"])
        self.assertIn("Hausa", data["languages"])
        self.assertEqual(data["max_message_chars"], config.MAX_MESSAGE_CHARS)

    def test_conversation_lifecycle(self):
        created = self.client.post("/api/conversations")
        self.assertEqual(created.status_code, 200)
        conversation_id = created.json()["id"]

        listed = self.client.get("/api/conversations").json()["conversations"]
        self.assertEqual(listed[0]["id"], conversation_id)

        renamed = self.client.patch(f"/api/conversations/{conversation_id}", json={"title": "  Physics   revision "})
        self.assertEqual(renamed.json()["title"], "Physics revision")

        fetched = self.client.get(f"/api/conversations/{conversation_id}").json()
        self.assertEqual(fetched["title"], "Physics revision")
        self.assertEqual(fetched["messages"], [])

        self.assertEqual(self.client.delete(f"/api/conversations/{conversation_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/conversations/{conversation_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/conversations/{conversation_id}").status_code, 404)

    def test_clear_all_conversations(self):
        self.client.post("/api/conversations")
        self.client.post("/api/conversations")

        response = self.client.delete("/api/conversations")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": 2})
        self.assertEqual(self.client.get("/api/conversations").json()["conversations"], [])

    def test_conversation_list_includes_message_counts(self):
        conversation_id = self.client.post("/api/conversations").json()["id"]
        con = store.connect(self.db)
        try:
            store.append_message(con, conversation_id, "user", "What is force?")
            store.append_message(con, conversation_id, "assistant", "A push or a pull.")
        finally:
            con.close()

        listed = self.client.get("/api/conversations").json()["conversations"]

        self.assertEqual(listed[0]["id"], conversation_id)
        self.assertEqual(listed[0]["messages"], 2)

    def test_export_a_conversation_as_markdown(self):
        conversation_id = self.client.post("/api/conversations").json()["id"]
        con = store.connect(self.db)
        try:
            store.append_message(con, conversation_id, "user", "What is force?")
            store.append_message(con, conversation_id, "assistant", "A push or a pull.")
        finally:
            con.close()

        response = self.client.get(f"/api/conversations/{conversation_id}/export")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response.headers["content-type"])
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertIn("offlinescholar-new-chat.md", response.headers["content-disposition"])
        self.assertIn("# New chat", response.text)
        self.assertIn("**You**\n\nWhat is force?", response.text)
        self.assertIn("**OfflineScholar**\n\nA push or a pull.", response.text)

    def test_exporting_an_unknown_conversation_returns_404(self):
        response = self.client.get("/api/conversations/99999/export")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Conversation not found")

    def test_deleting_an_unknown_conversation_returns_404(self):
        response = self.client.delete("/api/conversations/99999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Conversation not found")

    def test_chat_rejects_an_oversized_message(self):
        with mock.patch.object(config, "MAX_MESSAGE_CHARS", 10):
            response = self.client.post("/api/chat", json={"message": "x" * 11})
        self.assertEqual(response.status_code, 400)
        self.assertIn("too long", response.json()["detail"])
        con = store.connect(self.db)
        try:
            self.assertEqual(store.list_conversations(con), [])
        finally:
            con.close()

    def test_chat_streams_and_saves_messages(self):
        def fake_stream(history, message, mode, language, use_notes, model, passages=None, use_web=False, web_sink=None):
            self.assertEqual(message, "What is chlorophyll?")
            self.assertEqual(model, "gemma3:1b")
            yield "Chlorophyll "
            yield "absorbs light."

        with mock.patch.object(server.services, "answer_stream", side_effect=fake_stream):
            response = self.client.post("/api/chat", json={
                "message": "What is chlorophyll?",
                "mode": "Explain simply",
                "language": "English",
                "model": "gemma3:1b",
            })

        self.assertEqual(response.status_code, 200)
        self.assertIn('"type": "start"', response.text)
        self.assertIn('"type": "token"', response.text)
        self.assertIn('"type": "done"', response.text)

        con = store.connect(self.db)
        try:
            conversations = store.list_conversations(con)
            self.assertEqual(len(conversations), 1)
            self.assertEqual(conversations[0]["title"], "What is chlorophyll?")
            messages = store.conversation_messages(con, conversations[0]["id"])
        finally:
            con.close()
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])
        self.assertEqual(messages[1]["content"], "Chlorophyll absorbs light.")

    def test_chat_reports_sources_and_verifies_citations(self):
        passage = {"path": "/tmp/photosynthesis.txt", "label": "part 2",
                   "text": "Plants release oxygen.", "score": 0.81}

        def fake_stream(history, message, mode, language, use_notes, model, passages=None, use_web=False, web_sink=None):
            self.assertEqual(passages, [passage])
            yield "Plants release oxygen [1]."

        with mock.patch.object(server.services, "retrieve", return_value=[passage]), \
                mock.patch.object(server.services, "answer_stream", side_effect=fake_stream):
            response = self.client.post("/api/chat", json={"message": "What do plants release?"})

        self.assertIn('"type": "sources"', response.text)
        self.assertIn("photosynthesis.txt", response.text)
        self.assertIn('"grounded": true', response.text)

    def test_chat_ignores_web_lookup_requests(self):
        def fake_stream(history, message, mode, language, use_notes, model, passages=None,
                        use_web=False, web_sink=None):
            self.assertFalse(use_web)
            yield "Current facts are unavailable offline."

        with mock.patch.object(server.services, "retrieve", return_value=[]), \
                mock.patch.object(server.services, "answer_stream", side_effect=fake_stream):
            response = self.client.post("/api/chat", json={
                "message": "Who is the current governor of Gombe State?",
                "use_web": True,
            })

        self.assertNotIn('"type": "sources"', response.text)
        self.assertIn('"web_used": false', response.text)

    def test_chat_hides_sources_when_notes_do_not_cover_the_question(self):
        passage = {"path": "/tmp/newtons_laws.txt", "label": "part 1",
                   "text": "Newton described three laws.", "score": 0.7}

        def fake_stream(history, message, mode, language, use_notes, model, passages=None, use_web=False, web_sink=None):
            yield "Your notes do not cover that."

        with mock.patch.object(server.services, "retrieve", return_value=[passage]), \
                mock.patch.object(server.services, "answer_stream", side_effect=fake_stream):
            response = self.client.post("/api/chat", json={"message": "What is the fourth law?"})

        self.assertNotIn('"type": "sources"', response.text)
        self.assertIn('"notes_used": true', response.text)

    def test_chat_error_is_friendly(self):
        def explode(*_args, **_kwargs):
            raise RuntimeError("model 'missing' not found")
            yield  # pragma: no cover

        with mock.patch.object(server.services, "answer_stream", side_effect=explode):
            response = self.client.post("/api/chat", json={"message": "hi", "model": "missing"})
        self.assertIn("ollama pull missing", response.text)

    def test_upload_response_reports_whether_files_were_saved(self):
        files = [{"name": "cells.txt", "size": 2, "state": "indexed"}]
        with mock.patch.object(server.services, "add_uploads",
                               return_value=("Added cells.txt", True)), \
                mock.patch.object(server.services, "library_files", return_value=files), \
                mock.patch.object(server.services, "notes_summary",
                                  return_value={"files": 1, "indexed": 1, "size": 2}):
            response = self.client.post(
                "/api/notes/upload",
                files=[("files", ("cells.txt", b"hi", "text/plain"))],
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        self.assertEqual(response.json()["message"], "Added cells.txt")

    def test_delete_note_endpoint_forwards_the_name(self):
        with mock.patch.object(server.services, "remove_note",
                               return_value="Removed cells.txt") as remove_note, \
                mock.patch.object(server.services, "library_files", return_value=[]), \
                mock.patch.object(server.services, "notes_summary",
                                  return_value={"files": 0, "indexed": 0, "size": 0}):
            response = self.client.delete("/api/notes", params={"name": "cells.txt"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Removed cells.txt")
        remove_note.assert_called_once_with("cells.txt")

    def test_notes_endpoints(self):
        files = [{"name": "cells.txt", "size": 64, "state": "indexed"}]
        summary = {"files": 1, "indexed": 1, "size": 64}
        with mock.patch.object(server.services, "library_files", return_value=files), \
                mock.patch.object(server.services, "notes_summary", return_value=summary), \
                mock.patch.object(server.services, "scan_notes", return_value="Scanned 1 file"):
            notes = self.client.get("/api/notes").json()
            self.assertEqual(notes["files"][0]["name"], "cells.txt")
            rescan = self.client.post("/api/notes/rescan").json()
            self.assertEqual(rescan["message"], "Scanned 1 file")


if __name__ == "__main__":
    unittest.main()
