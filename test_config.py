"""Tests for the environment helpers used by the settings module."""
import os
import unittest
from pathlib import Path
from unittest import mock

import config


class EnvironmentHelperTests(unittest.TestCase):
    def test_int_env_reads_and_clamps(self):
        with mock.patch.dict(os.environ, {"OS_TEST_INT": "999"}, clear=False):
            self.assertEqual(config._int_env("OS_TEST_INT", 10, minimum=20), 999)
        with mock.patch.dict(os.environ, {"OS_TEST_INT": "1"}, clear=False):
            self.assertEqual(config._int_env("OS_TEST_INT", 10, minimum=20), 20)

    def test_int_env_falls_back_for_missing_or_bad_values(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config._int_env("OS_TEST_INT", 10), 10)
        with mock.patch.dict(os.environ, {"OS_TEST_INT": "not-a-number"}, clear=True):
            self.assertEqual(config._int_env("OS_TEST_INT", 10), 10)

    def test_float_env_clamps_to_the_range(self):
        with mock.patch.dict(os.environ, {"OS_TEST_FLOAT": "5"}, clear=True):
            self.assertEqual(config._float_env("OS_TEST_FLOAT", 0.5, 0.0, 2.0), 2.0)
        with mock.patch.dict(os.environ, {"OS_TEST_FLOAT": "-1"}, clear=True):
            self.assertEqual(config._float_env("OS_TEST_FLOAT", 0.5, 0.0, 2.0), 0.0)

    def test_bool_env_accepts_common_true_and_false_values(self):
        for value in ("1", "true", "YES", "on"):
            with mock.patch.dict(os.environ, {"OS_TEST_BOOL": value}, clear=True):
                self.assertTrue(config._bool_env("OS_TEST_BOOL", False), value)
        for value in ("0", "false", "no", "off", "anything"):
            with mock.patch.dict(os.environ, {"OS_TEST_BOOL": value}, clear=True):
                self.assertFalse(config._bool_env("OS_TEST_BOOL", True), value)

    def test_path_env_expands_the_home_folder(self):
        with mock.patch.dict(os.environ, {"OS_TEST_PATH": "~/study-notes"}, clear=True):
            self.assertEqual(config._path_env("OS_TEST_PATH", Path("/default")),
                             Path.home() / "study-notes")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config._path_env("OS_TEST_PATH", Path("/default")), Path("/default"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
