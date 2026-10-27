"""Tests for conversation storage, formatting and cleanup."""
import tempfile
import unittest
from pathlib import Path

import store


class TitleTests(unittest.TestCase):
    def test_titles_are_collapsed_and_capped(self):
        self.assertEqual(store.clean_title("  Physics   revision "), "Physics revision")
        self.assertEqual(store.clean_title("x" * 100, limit=10), "x" * 10)
        self.assertEqual(store.clean_title(None), "")


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

    def test_conversation_title_returns_none_for_a_missing_chat(self):
        conversation_id = store.create_conversation(self.con, "Physics")
        self.assertEqual(store.conversation_title(self.con, conversation_id), "Physics")
        self.assertIsNone(store.conversation_title(self.con, 9999))

    def test_list_reports_the_number_of_messages(self):
        conversation_id = store.create_conversation(self.con, "Physics")
        store.append_message(self.con, conversation_id, "user", "one")
        store.append_message(self.con, conversation_id, "assistant", "two")

        listed = store.list_conversations(self.con)

        self.assertEqual(listed[0]["id"], conversation_id)
        self.assertEqual(listed[0]["messages"], 2)

    def test_clear_conversations_removes_every_chat_and_message(self):
        first = store.create_conversation(self.con, "Physics")
        second = store.create_conversation(self.con, "Chemistry")
        store.append_message(self.con, first, "user", "one")
        store.append_message(self.con, second, "user", "two")

        self.assertEqual(store.clear_conversations(self.con), 2)

        self.assertEqual(store.list_conversations(self.con), [])
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)

    def test_an_unknown_conversation_returns_none(self):
        self.assertIsNone(store.conversation_markdown(self.con, 9999))


if __name__ == "__main__":
    unittest.main(verbosity=2)
