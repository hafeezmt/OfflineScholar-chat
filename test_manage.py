"""Tests for the start/stop command helpers. No server is started."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import manage


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


class ModelOverrideTests(unittest.TestCase):
    def test_low_memory_auto_picks_for_the_default_model(self):
        with mock.patch.object(manage.config, "LOW_MEMORY", True):
            self.assertIsNone(manage._model_override({"chat_model": manage.DEFAULT_CHAT_MODEL}))

    def test_an_explicit_choice_is_respected(self):
        with mock.patch.object(manage.config, "LOW_MEMORY", True):
            self.assertEqual(
                manage._model_override({"chat_model": "qwen2.5:1.5b"}), "qwen2.5:1.5b")

    def test_high_memory_keeps_the_settings_model(self):
        with mock.patch.object(manage.config, "LOW_MEMORY", False):
            self.assertEqual(
                manage._model_override({"chat_model": manage.DEFAULT_CHAT_MODEL}),
                manage.DEFAULT_CHAT_MODEL)


class ProcessTests(unittest.TestCase):
    def test_current_process_is_alive(self):
        self.assertTrue(manage._pid_alive(os.getpid()))

    def test_missing_process_is_not_alive(self):
        self.assertFalse(manage._pid_alive(99999999))

    def test_url_uses_port(self):
        self.assertEqual(manage.server_url(9000), "http://127.0.0.1:9000")


class CommandLineTests(unittest.TestCase):
    def test_up_passes_the_port_and_no_open_flag(self):
        with mock.patch.object(manage, "start",
                               return_value=("http://127.0.0.1:9000", True, {})) as start, \
                contextlib.redirect_stdout(io.StringIO()):
            code = manage.main(["up", "--port", "9000", "--no-open"])
        self.assertEqual(code, 0)
        start.assert_called_once_with(port=9000, open_browser=False)

    def test_stop_passes_the_port(self):
        with mock.patch.object(manage, "stop", return_value=True) as stop, \
                contextlib.redirect_stdout(io.StringIO()):
            code = manage.main(["stop", "--port", "9000"])
        self.assertEqual(code, 0)
        stop.assert_called_once_with(port=9000)

    def test_restart_uses_the_port_for_both_steps(self):
        with mock.patch.object(manage, "stop") as stop, \
                mock.patch.object(manage, "start",
                                  return_value=("http://127.0.0.1:9000", True, {})) as start, \
                contextlib.redirect_stdout(io.StringIO()):
            code = manage.main(["restart", "--port", "9000"])
        self.assertEqual(code, 0)
        stop.assert_called_once_with(port=9000)
        start.assert_called_once_with(port=9000, open_browser=True)

    def test_status_json_reports_a_stopped_app(self):
        output = io.StringIO()
        with mock.patch.object(manage, "fetch_status", return_value=None), \
                contextlib.redirect_stdout(output):
            code = manage.main(["status", "--json", "--port", "9000"])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["running"])
        self.assertEqual(payload["url"], "http://127.0.0.1:9000")

    def test_status_json_includes_the_live_server_fields(self):
        output = io.StringIO()
        with mock.patch.object(manage, "fetch_status",
                               return_value={"model": "gemma3:1b", "low_memory": True}), \
                contextlib.redirect_stdout(output):
            code = manage.main(["status", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertTrue(payload["running"])
        self.assertEqual(payload["model"], "gemma3:1b")
        self.assertTrue(payload["low_memory"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
