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
        self.assertEqual(self.client.get("/favicon.svg").status_code, 200)

    def test_status_reports_models_and_modes(self):
        with mock.patch.object(server.llm, "list_models", return_value=["gemma3:1b"]), \
                mock.patch.object(server.services, "notes_summary", return_value={"files": 0, "indexed": 0, "size": 0}):
            data = self.client.get("/api/status").json()
        self.assertTrue(data["ollama"])
        self.assertIn("gemma3:1b", data["models"])
        self.assertIn("Quiz me", data["modes"])
        self.assertIn("Hausa", data["languages"])

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
