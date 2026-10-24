#!/usr/bin/env python3
"""
Regresión del setup y del doctor (`lib/core/setup.py`).

Dos cosas importan acá:

1. Guardar una clave no puede duplicar líneas ni crear archivos de shell que el
   usuario no tenía. Se actualiza lo que existe.
2. Una clave nunca se imprime entera. El doctor y el setup muestran un prefijo y
   un sufijo; el valor completo no puede terminar en la terminal.
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from lib.core import setup


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

        patcher = mock.patch.object(setup.Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)

        self._env = dict(os.environ)
        self.addCleanup(self._restore)

        # El entorno del desarrollador puede tener claves reales cargadas:
        # ningún test debe depender de eso.
        for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY",
                    "OPENAI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"):
            os.environ.pop(key, None)

    def _restore(self):
        os.environ.clear()
        os.environ.update(self._env)

    def write(self, relative, body):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path


class SaveKey(Base):

    def test_it_sets_the_variable_in_the_current_process(self):
        setup.save_key_to_shells("MI_CLAVE", "valor")
        self.assertEqual(os.environ["MI_CLAVE"], "valor")

    def test_it_appends_to_an_existing_bashrc(self):
        bashrc = self.write(".bashrc", "alias ll='ls -l'\n")

        setup.save_key_to_shells("MI_CLAVE", "valor")

        content = bashrc.read_text(encoding="utf-8")
        self.assertIn("alias ll='ls -l'", content)
        self.assertIn('export MI_CLAVE="valor"', content)

    def test_it_replaces_an_old_value_instead_of_duplicating(self):
        bashrc = self.write(".bashrc", 'export MI_CLAVE="viejo"\nexport OTRA="x"\n')

        setup.save_key_to_shells("MI_CLAVE", "nuevo")

        content = bashrc.read_text(encoding="utf-8")
        self.assertNotIn("viejo", content)
        self.assertEqual(content.count("export MI_CLAVE="), 1)
        self.assertIn('export MI_CLAVE="nuevo"', content)
        self.assertIn('export OTRA="x"', content)

    def test_it_does_not_create_shell_files_that_were_absent(self):
        setup.save_key_to_shells("MI_CLAVE", "valor")

        self.assertFalse((self.home / ".bashrc").exists())
        self.assertFalse((self.home / ".zshrc").exists())

    def test_it_updates_zshrc_too(self):
        zshrc = self.write(".zshrc", "")

        setup.save_key_to_shells("MI_CLAVE", "valor")

        self.assertIn('export MI_CLAVE="valor"', zshrc.read_text(encoding="utf-8"))

    def test_it_writes_the_fish_secrets_file_when_the_directory_exists(self):
        (self.home / ".config" / "fish" / "conf.d").mkdir(parents=True)

        setup.save_key_to_shells("MI_CLAVE", "valor")

        content = (self.home / ".config/fish/conf.d/secrets.fish").read_text(encoding="utf-8")
        self.assertIn("set -gx MI_CLAVE 'valor'", content)

    def test_fish_is_updated_not_duplicated(self):
        (self.home / ".config" / "fish" / "conf.d").mkdir(parents=True)
        self.write(".config/fish/conf.d/secrets.fish", "set -gx MI_CLAVE 'viejo'\n")

        setup.save_key_to_shells("MI_CLAVE", "nuevo")
        setup.save_key_to_shells("MI_CLAVE", "nuevo")

        content = (self.home / ".config/fish/conf.d/secrets.fish").read_text(encoding="utf-8")
        self.assertEqual(content.count("set -gx MI_CLAVE "), 1)
        self.assertIn("nuevo", content)

    def test_without_the_fish_directory_it_does_not_create_it(self):
        setup.save_key_to_shells("MI_CLAVE", "valor")

        self.assertFalse((self.home / ".config").exists())


class CommandSetup(Base):

    def _run(self, env=None, answer=""):
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False), \
                mock.patch.object(setup, "banner"), \
                mock.patch.object(setup, "save_key_to_shells") as save, \
                mock.patch("builtins.input", return_value=answer), \
                redirect_stdout(buffer):
            setup.cmd_setup()
        return save, buffer.getvalue()

    def test_an_existing_key_is_not_requested_again(self):
        with mock.patch("builtins.input") as ask:
            ask.side_effect = AssertionError("no debería preguntar")
            self._run({"GEMINI_API_KEY": "AIzaSyCLAVEexistente"})

        self.assertFalse(ask.called)

    def test_a_provided_key_is_saved_under_both_names(self):
        save, _ = self._run({"GEMINI_API_KEY": ""}, answer="AIzaNueva")

        saved = {call.args[0] for call in save.call_args_list}
        self.assertEqual(saved, {"GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY"})

    def test_an_empty_answer_saves_nothing(self):
        save, _ = self._run({"GEMINI_API_KEY": ""}, answer="")

        save.assert_not_called()

    def test_the_full_key_never_reaches_the_terminal(self):
        secret = "AIzaSyCLAVEcompletasecreta123456"
        _, output = self._run({"GEMINI_API_KEY": secret})

        self.assertNotIn(secret, output)


class CommandDoctor(Base):

    def _run(self, env=None, which=None):
        buffer = io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False), \
                mock.patch.object(setup, "banner"), \
                mock.patch.object(setup, "find_hurl_runner", return_value=None), \
                mock.patch.object(setup, "find_opencode_runner", return_value=None), \
                mock.patch.object(setup, "find_prism_runner", return_value=None), \
                mock.patch.object(setup.shutil, "which", side_effect=lambda name: (which or {}).get(name)), \
                mock.patch.object(setup.Path, "exists", return_value=False), \
                redirect_stdout(buffer):
            setup.cmd_doctor()
        return buffer.getvalue()

    def test_it_reports_the_native_mock_when_prism_is_missing(self):
        self.assertIn("Mock Server Nativo", self._run())

    def test_it_reports_prism_when_available(self):
        with mock.patch.object(setup, "find_prism_runner", return_value=["npx", "--yes", "prism"]):
            buffer = io.StringIO()
            with mock.patch.object(setup, "banner"), \
                    mock.patch.object(setup, "find_hurl_runner", return_value=None), \
                    mock.patch.object(setup, "find_opencode_runner", return_value=None), \
                    mock.patch.object(setup.shutil, "which", return_value=None), \
                    mock.patch.object(setup.Path, "exists", return_value=False), \
                    redirect_stdout(buffer):
                setup.cmd_doctor()

        self.assertIn("Prism", buffer.getvalue())

    def test_configured_keys_are_masked(self):
        secret = "AIzaSyCLAVEcompletasecreta123456"
        output = self._run({"GEMINI_API_KEY": secret})

        self.assertIn("AIza", output)
        self.assertNotIn(secret, output)


if __name__ == "__main__":
    unittest.main()
