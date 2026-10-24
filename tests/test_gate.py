#!/usr/bin/env python3
"""
Regresión del freno de cambios (`lib/core/gate.py`).

El gate es la pieza que puede bloquear trabajo, así que lo que fija este
archivo es el borde exacto de la regla y no una descripción vaga de ella:

1. El límite es 10 archivos: 10 pasa, 11 bloquea. Un `>` que se convierta en
   `>=`, o al revés, cambia la respuesta del arnés entero.
2. Al bloquear, el mensaje nombra los archivos que lo dispararon: un freno que
   no dice qué lo activó no se puede resolver.
3. Dentro del límite no imprime nada, para no ensuciar el pipeline.
4. `check_git_repo` sólo inicializa cuando de verdad no hay repositorio.
5. El MCP y el gate coinciden en el mismo borde: las dos superficies no pueden
   dar respuestas opuestas para el mismo workspace.
"""

import subprocess
import unittest
from unittest import mock

from lib.core import gate


def _fake_git(stdout="", returncode=0):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr="")


class GitStatus(unittest.TestCase):

    def _run(self, stdout, returncode=0):
        with mock.patch.object(
            subprocess, "run", return_value=_fake_git(stdout, returncode)
        ) as run:
            result = gate.get_git_status()
        return result, run

    def test_counts_only_real_entries(self):
        stdout = " M lib/a.py\n?? lib/b.py\n\n   \n"
        (count, files), _ = self._run(stdout)

        self.assertEqual(count, 2)
        self.assertEqual(files, [" M lib/a.py", "?? lib/b.py"])

    def test_empty_workspace_is_zero(self):
        (count, files), _ = self._run("\n\n")

        self.assertEqual(count, 0)
        self.assertEqual(files, [])

    def test_reads_porcelain_status(self):
        _, run = self._run("")

        run.assert_called_once_with(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        )


class AuditChangesRule(unittest.TestCase):

    def _audit(self, count):
        """Corre la regla con `count` archivos y devuelve (resultado, mensajes)."""
        printed = []
        files = [f"  M archivo{i}.py" for i in range(count)]

        with mock.patch.object(gate, "get_git_status", return_value=(count, files)), \
                mock.patch.object(gate, "smooth_print", side_effect=printed.append):
            allowed = gate.audit_changes_rule()

        return allowed, printed

    def test_the_limit_itself_is_allowed(self):
        allowed, _ = self._audit(gate.MAX_ALLOWED_CHANGES)

        self.assertTrue(allowed)

    def test_one_over_the_limit_blocks(self):
        allowed, _ = self._audit(gate.MAX_ALLOWED_CHANGES + 1)

        self.assertFalse(allowed)

    def test_the_limit_is_ten(self):
        self.assertEqual(gate.MAX_ALLOWED_CHANGES, 10)
        self.assertTrue(self._audit(10)[0])
        self.assertFalse(self._audit(11)[0])

    def test_blocking_names_every_file(self):
        _, printed = self._audit(12)
        text = "\n".join(printed)

        self.assertIn("DISYUNTOR", text)
        self.assertIn("12 archivos", text)
        for index in range(12):
            self.assertIn(f"archivo{index}.py", text)

    def test_allowing_prints_nothing(self):
        _, printed = self._audit(3)

        self.assertEqual(printed, [])


class CheckGitRepo(unittest.TestCase):

    def test_inside_a_repo_does_not_initialize(self):
        with mock.patch.object(subprocess, "run", return_value=_fake_git("", 0)), \
                mock.patch("lib.core.init_project.cmd_init") as init:
            gate.check_git_repo()

        init.assert_not_called()

    def test_outside_a_repo_initializes_once(self):
        with mock.patch.object(subprocess, "run", return_value=_fake_git("", 128)), \
                mock.patch.object(gate, "smooth_print"), \
                mock.patch("lib.core.init_project.cmd_init") as init:
            gate.check_git_repo()

        init.assert_called_once_with()

    def test_detection_uses_git_rev_parse(self):
        with mock.patch.object(subprocess, "run", return_value=_fake_git("", 0)) as run, \
                mock.patch("lib.core.init_project.cmd_init"):
            gate.check_git_repo()

        run.assert_called_once_with(
            ["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True
        )


class McpAgreesWithTheGate(unittest.TestCase):
    """El MCP no puede contestar distinto que el gate para el mismo conteo."""

    def _audit_via_mcp(self, count):
        from lib.mcp.handlers import governance

        files = [f" M archivo{i}.py" for i in range(count)]
        with mock.patch.object(gate, "get_git_status", return_value=(count, files)):
            return governance.h_audit_changes({})

    def test_both_allow_the_limit(self):
        self.assertTrue(self._audit_via_mcp(gate.MAX_ALLOWED_CHANGES)["is_safe"])
        self.assertEqual(self._audit_via_mcp(gate.MAX_ALLOWED_CHANGES)["limit"], gate.MAX_ALLOWED_CHANGES)

    def test_both_block_one_over(self):
        over = gate.MAX_ALLOWED_CHANGES + 1
        self.assertFalse(self._audit_via_mcp(over)["is_safe"])
        with mock.patch.object(gate, "get_git_status", return_value=(over, [])), \
                mock.patch.object(gate, "smooth_print"):
            self.assertFalse(gate.audit_changes_rule())


if __name__ == "__main__":
    unittest.main()
