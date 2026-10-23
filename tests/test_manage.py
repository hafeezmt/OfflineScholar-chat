"""Tests for the start/stop command helpers. No server is started."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from offlinescholar import manage


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "settings.json"
        self.old_path = manage.SETTINGS_FILE
        manage.SETTINGS_FILE = self.path

    def tearDown(self):
        manage.SETTINGS_FILE = self.old_path
        self.tmp.cleanup()

    def test_defaults_are_usable(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = manage.load_settings()
        self.assertEqual(settings["port"], 7860)
        self.assertTrue(settings["chat_model"])
        self.assertTrue(settings["embed_model"])

    def test_file_and_environment_precedence(self):
        self.path.write_text(
            '{"chat_model": "file-model", "embed_model": "file-embed", "port": 8100}',
            encoding="utf-8")
        with mock.patch.dict(os.environ, {"OS_PORT": "8200", "OS_MODEL": "env-model"}, clear=True):
            settings = manage.load_settings()
        self.assertEqual(settings["port"], 8200)
        self.assertEqual(settings["chat_model"], "env-model")
        self.assertEqual(settings["embed_model"], "file-embed")

    def test_bad_settings_file_falls_back(self):
        self.path.write_text("not json", encoding="utf-8")
        with mock.patch.dict(os.environ, {}, clear=True):
            settings = manage.load_settings()
        self.assertEqual(settings["port"], 7860)


class ProcessTests(unittest.TestCase):
    def test_current_process_is_alive(self):
        self.assertTrue(manage._pid_alive(os.getpid()))

    def test_missing_process_is_not_alive(self):
        self.assertFalse(manage._pid_alive(99999999))

    def test_url_uses_port(self):
        self.assertEqual(manage.server_url(9000), "http://127.0.0.1:9000")


if __name__ == "__main__":
    unittest.main(verbosity=2)
