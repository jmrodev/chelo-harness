#!/usr/bin/env python3
"""
Regresión de canales: resolución de credenciales y ausencia de hardcodeos.

Tres cosas que este archivo fija:

1. El orden de búsqueda de secretos (entorno gana, luego CHELO_ENV_FILE, luego
   .env cercano, luego la config del usuario).
2. Ningún canal de Slack hardcodeado: sin SLACK_CHANNEL_ID el error lo dice y no
   se hace ninguna llamada de red.
3. Ningún nombre de publicación hardcodeado: `username` solo viaja en el payload
   si SLACK_USERNAME está definido.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.channels import secrets, slack

SECRET_KEYS = (
    "SLACK_USER_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_WEBHOOK_URL",
    "SLACK_CHANNEL_ID",
    "SLACK_CHANNEL_PRACTICAS",
    "SLACK_USERNAME",
    "CHELO_ENV_FILE",
)


class Isolated(unittest.TestCase):
    """Aísla entorno, cwd y la config del usuario para que el test sea hermético."""

    def setUp(self):
        # Snapshot completo: restaurar sólo las claves conocidas deja pasar las
        # que define cada test (TOKEN, por ejemplo) y contamina el siguiente.
        self._env_snapshot = dict(os.environ)
        self.addCleanup(self._restore_env)
        for key in SECRET_KEYS:
            os.environ.pop(key, None)

        self._original_cwd = Path.cwd()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, self._original_cwd)

        # La config del usuario no puede depender de la máquina que corre el test.
        # create=True para que el patch no reviente contra una versión anterior
        # que no tenía USER_CONFIG.
        patcher = mock.patch.object(
            secrets, "USER_CONFIG", Path(self.tmp.name) / "no-config/.env", create=True
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _restore_env(self):
        os.environ.clear()
        os.environ.update(self._env_snapshot)

    def write_env(self, name, body):
        path = Path(self.tmp.name) / name
        path.write_text(body, encoding="utf-8")
        return path


class TestSecretResolution(Isolated):

    def test_environment_wins_over_files(self):
        self.write_env(".env", "TOKEN=desde-archivo\n")
        os.environ["TOKEN"] = "desde-entorno"
        self.assertEqual(secrets.get_secret("TOKEN"), "desde-entorno")

    def test_chelo_env_file_is_read(self):
        path = self.write_env("otro.env", "TOKEN=desde-override\n")
        os.environ["CHELO_ENV_FILE"] = str(path)
        self.assertEqual(secrets.get_secret("TOKEN"), "desde-override")

    def test_local_dot_env_is_read(self):
        self.write_env(".env", "TOKEN=desde-local\n")
        self.assertEqual(secrets.get_secret("TOKEN"), "desde-local")

    def test_missing_key_returns_default(self):
        self.write_env(".env", "OTRA=1\n")
        self.assertEqual(secrets.get_secret("TOKEN", "fallback"), "fallback")

    def test_quotes_and_spaces_are_stripped(self):
        self.write_env(".env", 'TOKEN = "con-comillas"\n')
        self.assertEqual(secrets.get_secret("TOKEN"), "con-comillas")


class TestNoHardcodedChannel(Isolated):

    def test_messages_without_channel_reports_it_and_does_not_call_the_network(self):
        os.environ["SLACK_BOT_TOKEN"] = "xoxb-fake"

        with mock.patch.object(slack.urllib.request, "urlopen") as fake:
            result = slack.get_slack_messages()

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], slack.MISSING_CHANNEL)
        fake.assert_not_called()

    def test_post_without_channel_reports_it(self):
        os.environ["SLACK_BOT_TOKEN"] = "xoxb-fake"

        with mock.patch.object(slack.urllib.request, "urlopen") as fake:
            result = slack.post_slack_message("hola")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], slack.MISSING_CHANNEL)
        fake.assert_not_called()

    def test_channel_argument_wins(self):
        os.environ["SLACK_BOT_TOKEN"] = "xoxb-fake"
        os.environ["SLACK_CHANNEL_ID"] = "C-DESDE-ENTORNO"

        sent = []

        with mock.patch.object(slack.urllib.request, "urlopen", side_effect=_capture(sent)):
            slack.get_slack_messages(channel_id="C-EXPLICITO")

        self.assertIn("channel=C-EXPLICITO", sent[0].full_url)


class TestNoHardcodedUsername(Isolated):

    def _payload(self):
        os.environ["SLACK_BOT_TOKEN"] = "xoxb-fake"
        os.environ["SLACK_CHANNEL_ID"] = "C-1"

        sent = []
        with mock.patch.object(slack.urllib.request, "urlopen", side_effect=_capture(sent)):
            result = slack.post_slack_message("hola")

        self.assertTrue(result["ok"], result)
        return json.loads(sent[0].data.decode("utf-8"))

    def test_username_is_absent_by_default(self):
        self.assertNotIn("username", self._payload())

    def test_username_comes_from_the_environment(self):
        os.environ["SLACK_USERNAME"] = "quien-publica"
        self.assertEqual(self._payload()["username"], "quien-publica")


def _capture(sent):
    """Fabrica un urlopen falso que anota el request y responde ok."""

    class FakeResponse:
        def read(self):
            return b'{"ok": true}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake(request, timeout=None):
        sent.append(request)
        return FakeResponse()

    return fake


if __name__ == "__main__":
    unittest.main()
