"""Checks that the terminal front end stays quick to start and picks a model lazily."""
import contextlib
import io
import unittest
from unittest import mock

import cli
import llm


class CliTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
