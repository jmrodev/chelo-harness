#!/usr/bin/env python3
"""
Regresión del tablero (`lib/core/board.py`).

Lo que este archivo fija:

1. Cómo se lee el remoto: HTTPS, SSH y con o sin `.git` dan el mismo slug; un
   remoto que no es GitHub no inventa uno.
2. La URL del tablero se deriva del slug y sin slug no hay URL.
3. Configurar Pages: si `gh` no está o no tiene sesión, no se llama a la API;
   si el POST falla porque ya existe, se reintenta con PUT; si ambos fallan se
   devuelve el stderr real, no un mensaje vacío.
4. Inyectar el workflow: crea el archivo cuando falta, no pisa el existente sin
   `force`, y nunca reporta éxito fuera de un repositorio.
"""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from lib.core import board


def _git_result(stdout="", returncode=0):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr="")


class RepoSlug(unittest.TestCase):

    def _slug(self, stdout, returncode=0):
        with mock.patch.object(
            board.subprocess, "run", return_value=_git_result(stdout, returncode)
        ):
            return board.repo_slug()

    def test_https_remote(self):
        self.assertEqual(self._slug("https://github.com/jmrodev/chelo-harness.git\n"),
                         "jmrodev/chelo-harness")

    def test_https_remote_without_dot_git(self):
        self.assertEqual(self._slug("https://github.com/jmrodev/chelo-harness\n"),
                         "jmrodev/chelo-harness")

    def test_ssh_remote(self):
        self.assertEqual(self._slug("git@github.com:jmrodev/chelo-harness.git\n"),
                         "jmrodev/chelo-harness")

    def test_trailing_slash_is_ignored(self):
        self.assertEqual(self._slug("https://github.com/jmrodev/chelo-harness/\n"),
                         "jmrodev/chelo-harness")

    def test_a_non_github_remote_is_not_invented(self):
        self.assertIsNone(self._slug("https://gitlab.com/jmrodev/chelo-harness.git\n"))

    def test_a_failing_command_returns_none(self):
        self.assertIsNone(self._slug("", returncode=128))

    def test_it_asks_for_the_origin_url(self):
        with mock.patch.object(board.subprocess, "run", return_value=_git_result("")) as run:
            board.repo_slug()

        run.assert_called_once_with(
            ["git", "remote", "get-url", "origin"], capture_output=True, text=True
        )


class BoardUrl(unittest.TestCase):

    def test_url_from_slug(self):
        self.assertEqual(board.board_url("jmrodev/chelo-harness"),
                         "https://jmrodev.github.io/chelo-harness/")

    def test_no_slug_means_no_url(self):
        with mock.patch.object(board, "repo_slug", return_value=None):
            self.assertIsNone(board.board_url())

    def test_malformed_slug_is_rejected(self):
        self.assertIsNone(board.board_url("sin-barra"))


class GhAuthenticated(unittest.TestCase):

    def test_without_gh_it_does_not_run_anything(self):
        with mock.patch.object(board.shutil, "which", return_value=None), \
                mock.patch.object(board.subprocess, "run") as run:
            self.assertFalse(board.gh_authenticated())

        run.assert_not_called()

    def test_with_gh_it_asks_for_the_status(self):
        with mock.patch.object(board.shutil, "which", return_value="/usr/bin/gh"), \
                mock.patch.object(board.subprocess, "run", return_value=_git_result("", 0)) as run:
            self.assertTrue(board.gh_authenticated())

        run.assert_called_once_with(["gh", "auth", "status"], capture_output=True, text=True)

    def test_a_failed_status_is_not_authenticated(self):
        with mock.patch.object(board.shutil, "which", return_value="/usr/bin/gh"), \
                mock.patch.object(board.subprocess, "run", return_value=_git_result("", 4)):
            self.assertFalse(board.gh_authenticated())


class ConfigurePages(unittest.TestCase):

    def _configure(self, slug, responses):
        with mock.patch.object(board, "gh_authenticated", return_value=True), \
                mock.patch.object(board.subprocess, "run", side_effect=responses) as run:
            result = board.configure_pages(slug)
        return result, run

    def test_without_a_slug_it_does_not_call_the_api(self):
        with mock.patch.object(board.subprocess, "run") as run:
            ok, detail = board.configure_pages(None)

        self.assertFalse(ok)
        self.assertIn("origin", detail)
        run.assert_not_called()

    def test_without_an_authenticated_gh_it_does_not_call_the_api(self):
        with mock.patch.object(board, "gh_authenticated", return_value=False), \
                mock.patch.object(board.subprocess, "run") as run:
            ok, detail = board.configure_pages("jmrodev/repo")

        self.assertFalse(ok)
        self.assertIn("gh", detail)
        run.assert_not_called()

    def test_a_successful_post_enables_pages(self):
        created = mock.Mock(returncode=0, stdout="", stderr="")
        (ok, detail), run = self._configure("jmrodev/repo", [created])

        self.assertTrue(ok)
        self.assertIn("habilitado", detail)
        self.assertEqual(run.call_args.args[0][:4], ["gh", "api", "-X", "POST"])

    def test_an_existing_site_falls_back_to_put(self):
        created = mock.Mock(returncode=1, stdout="", stderr="already exists")
        updated = mock.Mock(returncode=0, stdout="", stderr="lo que sea")
        (ok, detail), run = self._configure("jmrodev/repo", [created, updated])

        self.assertTrue(ok)
        self.assertIn("actualizado", detail)
        self.assertEqual(run.call_args.args[0][:4], ["gh", "api", "-X", "PUT"])

    def test_both_failing_returns_the_real_stderr(self):
        created = mock.Mock(returncode=1, stdout="", stderr="")
        updated = mock.Mock(returncode=1, stdout="", stderr="HTTP 403: forbidden")
        (ok, detail), _ = self._configure("jmrodev/repo", [created, updated])

        self.assertFalse(ok)
        self.assertIn("403", detail)

    def test_both_failing_without_stderr_still_explains_itself(self):
        created = mock.Mock(returncode=1, stdout="", stderr="")
        updated = mock.Mock(returncode=1, stdout="", stderr="")
        (ok, detail), _ = self._configure("jmrodev/repo", [created, updated])

        self.assertFalse(ok)
        self.assertTrue(detail.strip())

    def test_the_api_paths_name_the_repository(self):
        created = mock.Mock(returncode=0, stdout="", stderr="")
        (_, _), run = self._configure("jmrodev/repo", [created])

        self.assertIn("repos/jmrodev/repo/pages", run.call_args.args[0])


class BoardInit(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        patcher = mock.patch.object(board, "repo_root", return_value=self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(board, "repo_slug", return_value="jmrodev/repo")
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.object(board, "configure_pages", return_value=(True, "ok"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def workflow(self):
        return self.root / board.WORKFLOW_RELATIVE

    def test_outside_a_repository_it_fails_explicitly(self):
        with mock.patch.object(board, "repo_root", return_value=None):
            result = board.board_init()

        self.assertFalse(result["ok"])
        self.assertIn("repositorio Git", result["error"])

    def test_it_creates_the_workflow_when_missing(self):
        result = board.board_init()

        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        self.assertTrue(self.workflow().is_file())
        self.assertIn("Deploy Project Board", self.workflow().read_text(encoding="utf-8"))

    def test_it_does_not_overwrite_an_existing_workflow(self):
        self.workflow().parent.mkdir(parents=True)
        self.workflow().write_text("propio", encoding="utf-8")

        result = board.board_init()

        self.assertFalse(result["created"])
        self.assertEqual(self.workflow().read_text(encoding="utf-8"), "propio")

    def test_force_overwrites(self):
        self.workflow().parent.mkdir(parents=True)
        self.workflow().write_text("propio", encoding="utf-8")

        result = board.board_init(force=True)

        self.assertTrue(result["created"])
        self.assertIn("Deploy Project Board", self.workflow().read_text(encoding="utf-8"))

    def test_it_reports_the_public_url(self):
        result = board.board_init()

        self.assertEqual(result["url"], "https://jmrodev.github.io/repo/")

    def test_pages_failure_becomes_manual_steps(self):
        with mock.patch.object(board, "configure_pages", return_value=(False, "sin sesión")):
            result = board.board_init()

        self.assertTrue(result["ok"])
        self.assertTrue(result["manual_steps"])
        self.assertEqual(result["pages_detail"], "sin sesión")

    def test_pages_success_needs_no_manual_steps(self):
        result = board.board_init()

        self.assertFalse(result["manual_steps"])


class CommandPresentation(unittest.TestCase):
    """La CLI informa si creó o encontró el workflow: son acciones distintas."""

    def _run(self, created):
        result = {
            "ok": True, "workflow": "x", "created": created, "slug": "jmrodev/repo",
            "pages_configured": True, "pages_detail": "ok",
            "url": "https://jmrodev.github.io/repo/", "manual_steps": False, "next": "push",
        }
        buffer = io.StringIO()
        with mock.patch.object(board, "check_git_repo"), \
                mock.patch.object(board, "banner"), \
                mock.patch.object(board, "board_init", return_value=result), \
                redirect_stdout(buffer):
            board.cmd_board_init()
        return buffer.getvalue()

    def test_it_says_created(self):
        self.assertIn("creado", self._run(True))

    def test_it_says_it_already_existed(self):
        self.assertIn("ya existía", self._run(False))


if __name__ == "__main__":
    unittest.main()
