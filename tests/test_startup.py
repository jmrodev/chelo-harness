#!/usr/bin/env python3
"""
Regresión del chequeo de arranque (`lib/core/startup.py`).

Este módulo decide si la sesión puede empezar. Dos errores concretos que fija:

1. "No hay ninguna API Key configurada" y devolver True no pueden convivir. Una
   clave con el valor `DISABLED` es una decisión explícita de no configurar.
2. Una herramienta instalada en el PATH está disponible, aunque no exista la
   copia en `~/.local/bin`. El ternario anterior la reportaba como ausente.
"""

import re
import unittest
from unittest import mock

from lib.core import startup

EMPTY_STACK = {
    "backend": None,
    "frontend": None,
    "package_manager": None,
    "has_openapi": False,
    "has_hurl": False,
    "has_docker": False,
}

KEYS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")


def plain(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", str(text))


class Base(unittest.TestCase):

    def run_check(self, env=None, which=None, local_hurl=False, stack=None, trace=False):
        lines = []

        home = mock.Mock()
        home.__truediv__ = lambda self_, other: mock.Mock(
            exists=lambda: local_hurl, __str__=lambda s: f"/home/tester/{other}"
        )

        with mock.patch.dict("os.environ", {}, clear=False), \
                mock.patch.dict("os.environ", env or {}, clear=False), \
                mock.patch.object(startup, "detect_workspace_stack", return_value=stack or EMPTY_STACK), \
                mock.patch.object(startup.shutil, "which", side_effect=lambda name: (which or {}).get(name)), \
                mock.patch.object(startup.Path, "home", return_value=home), \
                mock.patch.object(startup, "smooth_print", side_effect=lambda text="", delay=0.05: lines.append(plain(text))):
            for key in KEYS:
                if key not in (env or {}):
                    import os

                    os.environ.pop(key, None)
            result = startup.check_credentials_and_stack(trace=trace)

        return result, "\n".join(lines)


class Credentials(Base):

    def test_without_keys_it_cannot_start(self):
        result, output = self.run_check()

        self.assertFalse(result)
        self.assertIn("No hay ninguna API Key configurada", output)

    def test_a_gemini_key_allows_starting(self):
        result, _ = self.run_check({"GEMINI_API_KEY": "AIza-clave-real"})

        self.assertTrue(result)

    def test_an_alternative_key_allows_starting(self):
        result, _ = self.run_check({"OPENAI_API_KEY": "sk-clave-real"})

        self.assertTrue(result)

    def test_a_disabled_key_is_not_a_configured_key(self):
        """Decir 'no configurada' y devolver True es una contradicción."""
        result, output = self.run_check({"GEMINI_API_KEY": "DISABLED"})

        self.assertIn("Gemini API Key", output)
        self.assertFalse(result)

    def test_a_disabled_key_does_not_hide_a_real_one(self):
        result, _ = self.run_check(
            {"GEMINI_API_KEY": "DISABLED", "ANTHROPIC_API_KEY": "sk-ant-real"}
        )

        self.assertTrue(result)


class Tools(Base):

    def test_hurl_in_the_path_is_available(self):
        result, output = self.run_check(
            {"GEMINI_API_KEY": "AIza-real"}, which={"hurl": "/usr/bin/hurl"}
        )

        self.assertIn("hurl", output)
        self.assertNotIn("hurl: no detectado", output)

    def test_a_local_hurl_is_available(self):
        result, output = self.run_check(
            {"GEMINI_API_KEY": "AIza-real"}, which={}, local_hurl=True
        )

        self.assertNotIn("hurl: no detectado", output)

    def test_without_any_hurl_it_says_so(self):
        result, output = self.run_check({"GEMINI_API_KEY": "AIza-real"}, which={})

        self.assertIn("hurl", output)
        self.assertIn("no detectado", output)

    def test_gh_is_reported_from_the_path(self):
        result, output = self.run_check(
            {"GEMINI_API_KEY": "AIza-real"}, which={"gh": "/usr/bin/gh"}
        )

        self.assertIn("gh", output)
        self.assertNotIn("gh: no detectado", output)


class Presentation(Base):

    def test_an_empty_project_says_the_stack_is_unrecognized(self):
        result, output = self.run_check({"GEMINI_API_KEY": "AIza-real"})

        self.assertIn("Proyecto vacío", output)

    def test_a_detected_stack_is_named(self):
        stack = dict(EMPTY_STACK, backend="Python 3.12", has_openapi=True)
        result, output = self.run_check({"GEMINI_API_KEY": "AIza-real"}, stack=stack)

        self.assertIn("Python 3.12", output)
        self.assertIn("Contrato OpenAPI", output)

    def test_trace_is_announced(self):
        result, output = self.run_check({"GEMINI_API_KEY": "AIza-real"}, trace=True)

        self.assertIn("trazado", output.lower())

    def test_the_full_key_is_never_printed(self):
        secret = "AIzaSyCLAVEcompletasecreta123456"
        result, output = self.run_check({"GEMINI_API_KEY": secret})

        self.assertIn("AIza", output)
        self.assertNotIn(secret, output)


if __name__ == "__main__":
    unittest.main()
