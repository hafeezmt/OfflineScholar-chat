"""Tests for conversation storage, formatting and cleanup."""
import tempfile
import unittest
from pathlib import Path

import store


class ConversationMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = store.connect(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_markdown_includes_the_title_and_each_turn(self):
        conversation_id = store.create_conversation(self.con, "Physics revision")
        store.append_message(self.con, conversation_id, "user", "What is force?")
        store.append_message(self.con, conversation_id, "assistant", "A push or a pull [1].")

        markdown = store.conversation_markdown(self.con, conversation_id)

        self.assertTrue(markdown.startswith("# Physics revision\n"))
        self.assertIn("**You**\n\nWhat is force?", markdown)
        self.assertIn("**OfflineScholar**\n\nA push or a pull [1].", markdown)
        self.assertTrue(markdown.endswith("\n"))

    def test_an_empty_conversation_still_exports_its_title(self):
        conversation_id = store.create_conversation(self.con, "New chat")

        self.assertEqual(store.conversation_markdown(self.con, conversation_id), "# New chat\n")

    def test_an_unknown_conversation_returns_none(self):
        self.assertIsNone(store.conversation_markdown(self.con, 9999))


if __name__ == "__main__":
    unittest.main(verbosity=2)
