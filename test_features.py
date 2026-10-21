"""Tests for indexing, storage, uploads and the web-page reader. No Ollama or internet needed."""
import tempfile
import unittest
from pathlib import Path

import app
import config
import ingest
import llm
import store
import webpages


def temp_db(tmp):
    return store.connect(Path(tmp) / "test.db")


class ChunkTests(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(ingest.chunk_words("one two three", size=10), ["one two three"])

    def test_overlap_keeps_words_shared(self):
        chunks = ingest.chunk_words("a b c d e f", size=4, overlap=2)
        self.assertEqual(chunks, ["a b c d", "c d e f"])

    def test_empty_text_makes_no_chunks(self):
        self.assertEqual(ingest.chunk_words("   "), [])

    def test_zero_overlap_does_not_loop(self):
        chunks = ingest.chunk_words("a b c d", size=2, overlap=0)
        self.assertEqual(chunks, ["a b", "c d"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.con = temp_db(self.tmp.name)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_keyword_search_ignores_punctuation(self):
        store.add_chunks(self.con, "notes.txt", [("full", "Force equals mass times acceleration", None)])
        self.con.commit()
        hits = store.keyword_search(self.con, 'What is "force" (F=ma)?', 5)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["path"], "notes.txt")

    def test_keyword_search_with_only_stop_words_finds_nothing(self):
        store.add_chunks(self.con, "notes.txt", [("full", "the force is with you", None)])
        self.con.commit()
        self.assertEqual(store.keyword_search(self.con, "what is the", 5), [])

    def test_clear_index_keeps_files_table_empty(self):
        store.add_chunks(self.con, "notes.txt", [("full", "hello world", None)])
        self.con.execute("INSERT INTO files VALUES ('notes.txt', 1, 2, 0)")
        self.con.commit()
        store.clear_index(self.con)
        self.assertEqual(self.con.execute("SELECT count(*) FROM chunks").fetchone()[0], 0)
        self.assertEqual(self.con.execute("SELECT count(*) FROM files").fetchone()[0], 0)

    def test_embeddings_of_another_size_are_skipped(self):
        store.add_chunks(self.con, "a.txt", [("p", "alpha", [1, 0, 0, 0])])
        store.add_chunks(self.con, "b.txt", [("p", "beta", [1, 0, 0, 0, 0, 0, 0, 0])])
        self.con.commit()
        hits = store.semantic_search(self.con, [1, 0, 0, 0], 10)
        self.assertEqual([h["path"] for h in hits], ["a.txt"])


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.library = Path(self.tmp.name) / "library"
        self.library.mkdir()
        (self.library / "n.txt").write_text("force equals mass times acceleration")
        self.con = temp_db(self.tmp.name)
        self._old_model = config.EMBED_MODEL

    def tearDown(self):
        config.EMBED_MODEL = self._old_model
        self.con.close()
        self.tmp.cleanup()

    def test_switching_embedding_model_rebuilds_vectors(self):
        def embed_a(texts, query=False):
            return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

        def embed_b(texts, query=False):
            return [[0.0, 1.0, 0.0, 0.0] for _ in texts]

        config.EMBED_MODEL = "model-a"
        ingest.scan_library(self.con, embed_fn=embed_a, folder=self.library)
        self.assertEqual(store.get_meta(self.con, "embed_model"), "model-a")

        config.EMBED_MODEL = "model-b"
        message = ingest.scan_library(self.con, embed_fn=embed_b, folder=self.library)
        self.assertIn("Embedding model changed", message)
        self.assertEqual(store.get_meta(self.con, "embed_model"), "model-b")
        self.assertTrue(store.semantic_search(self.con, [0.0, 1.0, 0.0, 0.0], 3))

    def test_unreadable_file_is_not_left_indexed(self):
        bad = self.library / "broken.docx"
        bad.write_bytes(b"not a zip file")
        message = ingest.scan_library(self.con, folder=self.library)
        self.assertIn("Could not read broken.docx", message)
        self.assertEqual(
            self.con.execute("SELECT count(*) FROM chunks WHERE path=?", (str(bad),)).fetchone()[0], 0)

    def test_failed_embeddings_leave_model_unrecorded(self):
        config.EMBED_MODEL = "model-c"
        message = ingest.scan_library(
            self.con, embed_fn=lambda texts, query=False: [], folder=self.library)
        self.assertIn("Meaning-based search is off", message)
        self.assertIsNone(store.get_meta(self.con, "embed_model"))
        self.assertTrue(store.keyword_search(self.con, "force", 3))


class HistoryTests(unittest.TestCase):
    def test_normalize_dict_and_tuple_history(self):
        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "text", "text": "hi there"}]},
            ("question", "answer"),
            {"role": "user", "content": ""},
        ]
        msgs = app.normalize_history(history)
        self.assertEqual(msgs[0], {"role": "user", "content": "hello"})
        self.assertEqual(msgs[1], {"role": "assistant", "content": "hi there"})
        self.assertEqual(msgs[2:], [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ])

    def test_trim_starts_with_user_and_respects_zero(self):
        history = [{"role": "assistant", "content": "orphan"},
                   {"role": "user", "content": "q"},
                   {"role": "assistant", "content": "a"}]
        self.assertEqual(llm.trim_history(history, 2), history[1:])
        self.assertEqual(llm.trim_history(history, 0), [])


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = self.root / "library"
        self.library.mkdir()
        self._old_library = config.LIBRARY_DIR
        self._old_rescan = app.rescan
        config.LIBRARY_DIR = self.library
        app.rescan = lambda: "index checked"

    def tearDown(self):
        config.LIBRARY_DIR = self._old_library
        app.rescan = self._old_rescan
        self.tmp.cleanup()

    def test_add_updates_changed_file_and_skips_same_content(self):
        src = self.root / "notes.txt"
        src.write_text("first version")
        self.assertIn("Added 1 file(s)", app.add_files([str(src)]))
        self.assertIn("Already in library", app.add_files([str(src)]))
        src.write_text("second version")
        self.assertIn("Updated: notes.txt", app.add_files([str(src)]))
        self.assertEqual((self.library / "notes.txt").read_text(), "second version")

    def test_unsupported_file_is_reported(self):
        src = self.root / "program.exe"
        src.write_text("nope")
        message = app.add_files([str(src)])
        self.assertIn("not a supported type", message)
        self.assertFalse((self.library / "program.exe").exists())

    def test_empty_selection(self):
        self.assertEqual(app.add_files([]), "Choose one or more files first.")

    def test_library_list_reports_index_state(self):
        (self.library / "a.txt").write_text("hello")
        self.assertIn("not indexed", app.library_list())


class WebpageTests(unittest.TestCase):
    def test_parser_keeps_block_breaks_and_unskips_text(self):
        p = webpages._Text()
        p.feed("<title>A &amp; B</title><script>hidden</script><p>one</p><pre>x\ny</pre>")
        text = "".join(p.parts)
        self.assertEqual(p.title, "A & B")
        self.assertNotIn("hidden", text)
        self.assertIn("x\ny", text)

    def test_slug_is_unique_per_url(self):
        self.assertNotEqual(webpages._slug("Intro", "https://a.example"), webpages._slug("Intro", "https://b.example"))
        self.assertEqual(webpages._slug("Intro", "https://a.example"), webpages._slug("Intro", "https://a.example"))

    def test_rejects_non_http_links(self):
        self.assertIn("http", webpages.save_page("file:///etc/passwd"))


class UiTests(unittest.TestCase):
    def test_chat_history_is_saved(self):
        self.assertTrue(app.chat_ui.save_history)

    def test_theme_and_assets_are_available(self):
        self.assertTrue(app.CSS)
        self.assertTrue(app.AVATARS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
