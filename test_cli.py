"""Checks that the terminal front end stays quick to start and picks a model lazily."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import cli
import llm


class CliTests(unittest.TestCase):
    def test_export_prints_markdown(self):
        connection = mock.MagicMock()
        output = io.StringIO()
        with mock.patch.object(cli.store, "connect", return_value=connection), \
                mock.patch.object(cli.store, "conversation_markdown", return_value="# Physics\n\n**You**\n\nHi\n"), \
                contextlib.redirect_stdout(output):
            code = cli.main(["export", "7"])
        self.assertEqual(code, 0)
        self.assertEqual(output.getvalue(), "# Physics\n\n**You**\n\nHi\n")

    def test_export_writes_a_file(self):
        connection = mock.MagicMock()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cli.store, "connect", return_value=connection), \
                mock.patch.object(cli.store, "conversation_markdown", return_value="# Notes\n"), \
                contextlib.redirect_stdout(io.StringIO()):
            target = Path(tmp) / "chat.md"
            code = cli.main(["export", "7", "--output", str(target)])
            self.assertEqual(code, 0)
            self.assertEqual(target.read_text(encoding="utf-8"), "# Notes\n")

    def test_export_all_writes_one_file_per_chat(self):
        conversations = [
            {"id": 1, "title": "Physics revision", "updated": 0, "preview": "", "messages": 2},
            {"id": 2, "title": "Chemistry", "updated": 0, "preview": "", "messages": 1},
        ]
        markdown = {"1": "# Physics\n", "2": "# Chemistry\n"}
        connection = mock.MagicMock()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cli.store, "connect", return_value=connection), \
                mock.patch.object(cli.store, "list_conversations", return_value=conversations), \
                mock.patch.object(cli.store, "conversation_markdown",
                                  side_effect=lambda _con, chat_id: markdown[str(chat_id)]), \
                contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["export-all", tmp])
            self.assertEqual(code, 0)
            self.assertEqual((Path(tmp) / "1-physics-revision.md").read_text(), "# Physics\n")
            self.assertEqual((Path(tmp) / "2-chemistry.md").read_text(), "# Chemistry\n")

    def test_export_reports_a_missing_chat(self):
        connection = mock.MagicMock()
        output = io.StringIO()
        with mock.patch.object(cli.store, "connect", return_value=connection), \
                mock.patch.object(cli.store, "conversation_markdown", return_value=None), \
                contextlib.redirect_stdout(output):
            code = cli.main(["export", "99"])
        self.assertEqual(code, 1)
        self.assertIn("was not found", output.getvalue())

    def test_help_does_not_probe_ollama(self):
        with mock.patch.object(llm, "default_model") as default_model:
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
                cli.main(["ask", "--help"])
        self.assertEqual(raised.exception.code, 0)
        default_model.assert_not_called()

    def test_ask_resolves_the_model_only_when_answering(self):
        with mock.patch.object(llm, "default_model", return_value="tiny:latest") as default_model, \
                mock.patch.object(llm, "chat_stream", return_value=iter(["hello"])) as chat, \
                mock.patch.object(cli.services, "retrieve", return_value=[]) as retrieve, \
                contextlib.redirect_stdout(io.StringIO()):
            cli.main(["ask", "hi"])
        default_model.assert_called_once_with()
        retrieve.assert_called_once_with("hi")
        self.assertEqual(chat.call_args.kwargs["model"], "tiny:latest")

    def test_chats_lists_saved_conversations(self):
        conversation = {"id": 7, "title": "Physics revision", "updated": 0, "preview": "Newton"}
        connection = mock.MagicMock()
        output = io.StringIO()
        with mock.patch.object(cli.store, "connect", return_value=connection), \
                mock.patch.object(cli.store, "list_conversations", return_value=[conversation]), \
                contextlib.redirect_stdout(output):
            code = cli.main(["chats", "--limit", "5"])
        self.assertEqual(code, 0)
        self.assertIn("Physics revision", output.getvalue())
        self.assertIn("1 chat(s).", output.getvalue())
        connection.close.assert_called_once_with()

    def test_chats_can_print_json(self):
        conversation = {"id": 7, "title": "Physics revision", "updated": 0,
                        "preview": "Newton", "messages": 2}
        connection = mock.MagicMock()
        output = io.StringIO()
        with mock.patch.object(cli.store, "connect", return_value=connection), \
                mock.patch.object(cli.store, "list_conversations", return_value=[conversation]), \
                contextlib.redirect_stdout(output):
            code = cli.main(["chats", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())[0]["messages"], 2)

    def test_delete_removes_an_existing_chat(self):
        connection = mock.MagicMock()
        output = io.StringIO()
        with mock.patch.object(cli.store, "connect", return_value=connection), \
                mock.patch.object(cli.store, "conversation_exists", return_value=True), \
                mock.patch.object(cli.store, "delete_conversation") as delete, \
                contextlib.redirect_stdout(output):
            code = cli.main(["delete", "7"])
        self.assertEqual(code, 0)
        delete.assert_called_once_with(connection, 7)
        self.assertIn("Deleted chat 7", output.getvalue())

    def test_delete_reports_a_missing_chat(self):
        connection = mock.MagicMock()
        output = io.StringIO()
        with mock.patch.object(cli.store, "connect", return_value=connection), \
                mock.patch.object(cli.store, "conversation_exists", return_value=False), \
                mock.patch.object(cli.store, "delete_conversation") as delete, \
                contextlib.redirect_stdout(output):
            code = cli.main(["delete", "99"])
        self.assertEqual(code, 1)
        delete.assert_not_called()
        self.assertIn("was not found", output.getvalue())


if __name__ == "__main__":
    unittest.main()
