#!/usr/bin/env python3
"""
Regresión de la inicialización (`lib/core/init_project.py`).

Esta función escribe en proyectos ajenos, así que lo que fija este archivo es
lo que no debe pasar:

1. No pisa archivos existentes. Un `openapi.yaml` o un `AGENTS.md` con trabajo
   real no se puede perder porque alguien corra `init` de nuevo.
2. No inicializa un repo git dentro de otro. Detectarlo por `cwd/.git` falla en
   un subdirectorio, y ahí `git init` crea un repositorio anidado.
3. `git init` se lanza con `capture_output`, porque un subproceso hereda fd 1 y
   en el servidor MCP ese fd es el canal JSON-RPC.

Y lo que sí debe pasar: crear `docs/stories`, `tests`, un contrato base, la
constitución de gobernanza y un test de humo coherentes.
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from lib.core import init_project


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "mi-proyecto"
        self.project.mkdir()

        import os

        self._cwd = Path.cwd()
        os.chdir(self.project)
        self.addCleanup(os.chdir, self._cwd)

    def init(self, already_in_repo=False):
        """Corre cmd_init silenciando la presentación."""
        with mock.patch.object(init_project, "banner"), \
                mock.patch.object(init_project, "smooth_print"), \
                mock.patch.object(init_project, "_inside_git_repo", return_value=already_in_repo), \
                mock.patch.object(init_project.subprocess, "run") as run, \
                redirect_stdout(io.StringIO()):
            init_project.cmd_init()
        return run


class GitDetectionHelper(unittest.TestCase):
    """La detección en sí: es donde vive el bug del repo anidado."""

    def _check(self, stdout, returncode=0):
        with mock.patch.object(
            init_project.subprocess, "run", return_value=mock.Mock(returncode=returncode, stdout=stdout)
        ) as run:
            found = init_project._inside_git_repo()
        return found, run

    def test_it_believes_git(self):
        found, _ = self._check("true\n")
        self.assertTrue(found)

    def test_a_failed_command_means_no_repository(self):
        found, _ = self._check("", returncode=128)
        self.assertFalse(found)

    def test_any_other_answer_means_no_repository(self):
        found, _ = self._check("false\n")
        self.assertFalse(found)

    def test_it_asks_git_instead_of_looking_for_a_dot_git_directory(self):
        _, run = self._check("true\n")

        run.assert_called_once_with(
            ["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True
        )


class GitDetection(Base):

    def test_it_initializes_git_only_when_missing(self):
        run = self.init(already_in_repo=False)

        run.assert_called_once_with(
            ["git", "init"], check=True, capture_output=True, text=True
        )

    def test_it_does_not_reinitialize_an_existing_repository(self):
        run = self.init(already_in_repo=True)

        run.assert_not_called()

    def test_git_output_is_captured(self):
        """Sin capture_output, git escribe en el fd 1 y rompe el MCP."""
        run = self.init(already_in_repo=False)

        self.assertTrue(run.call_args.kwargs.get("capture_output"))


class Layout(Base):

    def test_it_creates_the_directories(self):
        self.init(already_in_repo=True)

        self.assertTrue((self.project / "docs" / "stories").is_dir())
        self.assertTrue((self.project / "tests").is_dir())

    def test_it_creates_a_valid_openapi_skeleton(self):
        self.init(already_in_repo=True)
        content = (self.project / "openapi.yaml").read_text(encoding="utf-8")

        self.assertIn("openapi: 3.0.3", content)
        self.assertIn(f"title: API {self.project.name}", content)
        self.assertIn("/health:", content)

    def test_it_creates_the_governance_file(self):
        self.init(already_in_repo=True)
        content = (self.project / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("PRINCIPIO SAGRADO", content)
        self.assertIn("10 archivos", content)

    def test_it_creates_the_smoke_test_with_the_contract_assertion(self):
        self.init(already_in_repo=True)
        content = (self.project / "tests" / "000_health.hurl").read_text(encoding="utf-8")

        self.assertIn("GET http://localhost:4010/health", content)
        self.assertIn('header "sl-violations" not exists', content)


class NothingIsOverwritten(Base):

    def test_an_existing_contract_survives(self):
        (self.project / "openapi.yaml").write_text("mío", encoding="utf-8")

        self.init(already_in_repo=True)

        self.assertEqual((self.project / "openapi.yaml").read_text(encoding="utf-8"), "mío")

    def test_an_existing_agents_file_survives(self):
        (self.project / "AGENTS.md").write_text("mío", encoding="utf-8")

        self.init(already_in_repo=True)

        self.assertEqual((self.project / "AGENTS.md").read_text(encoding="utf-8"), "mío")

    def test_an_existing_test_survives(self):
        tests = self.project / "tests"
        tests.mkdir()
        (tests / "000_health.hurl").write_text("mío", encoding="utf-8")

        self.init(already_in_repo=True)

        self.assertEqual((tests / "000_health.hurl").read_text(encoding="utf-8"), "mío")

    def test_running_twice_is_safe(self):
        self.init(already_in_repo=True)
        first = (self.project / "openapi.yaml").read_text(encoding="utf-8")

        self.init(already_in_repo=True)

        self.assertEqual((self.project / "openapi.yaml").read_text(encoding="utf-8"), first)


if __name__ == "__main__":
    unittest.main()
