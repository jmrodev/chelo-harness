#!/usr/bin/env python3
"""
Regresión de ubicación de recursos.

El defecto que fija: la CLI y el MCP tenían listas de rutas distintas, y sólo
una incluía el directorio donde `install.sh` deja los roles
(`~/.local/share/chelo/agents`). En una instalación limpia la CLI respondía
"Disponibles: (ninguno)" mientras el MCP listaba los siete roles.
"""

import tempfile
import unittest
from pathlib import Path

from lib.core import resources


class TestRoleCandidates(unittest.TestCase):

    def test_installer_location_is_searched(self):
        candidates = resources.role_candidates(
            home=Path("/home/tester"), cwd=Path("/proyecto"), package_root=Path("/paquete")
        )
        self.assertIn(Path("/home/tester/.local/share/chelo/agents"), candidates)

    def test_installer_location_wins_over_the_legacy_one(self):
        candidates = resources.role_candidates(
            home=Path("/home/tester"), cwd=Path("/proyecto"), package_root=Path("/paquete")
        )
        share = candidates.index(Path("/home/tester/.local/share/chelo/agents"))
        legacy = candidates.index(Path("/home/tester/.local/lib/chelo/agents"))
        self.assertLess(share, legacy)

    def test_project_agents_win_over_installed(self):
        candidates = resources.role_candidates(
            home=Path("/home/tester"), cwd=Path("/proyecto"), package_root=Path("/paquete")
        )
        self.assertEqual(candidates[0], Path("/proyecto/agents"))


class TestLocation(unittest.TestCase):
    """Escenarios sobre disco real, con home/cwd/paquete explícitos."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.home = base / "home"
        self.cwd = base / "proyecto"
        self.pkg = base / "paquete"
        for path in (self.home, self.cwd, self.pkg / "lib"):
            path.mkdir(parents=True)

    def _roles(self, where, names):
        where.mkdir(parents=True, exist_ok=True)
        for name in names:
            (where / f"{name}.md").write_text("rol", encoding="utf-8")
        return where

    def _locate(self):
        return resources.agents_dir(home=self.home, cwd=self.cwd, package_root=self.pkg)

    def _roles_found(self):
        return resources.available_roles(home=self.home, cwd=self.cwd, package_root=self.pkg)

    def test_fresh_install_finds_the_roles(self):
        """El escenario que antes devolvía cero roles en la CLI."""
        installed = self._roles(self.home / ".local" / "share" / "chelo" / "agents",
                                ["story-agent", "qa-tester"])

        self.assertEqual(self._locate(), installed)
        self.assertEqual(self._roles_found(), ["qa-tester", "story-agent"])

    def test_project_roles_override_the_installed_ones(self):
        self._roles(self.home / ".local" / "share" / "chelo" / "agents", ["instalado"])
        local = self._roles(self.cwd / "agents", ["propio"])

        self.assertEqual(self._locate(), local)
        self.assertEqual(self._roles_found(), ["propio"])

    def test_legacy_layout_still_resolves(self):
        legacy = self._roles(self.home / ".local" / "lib" / "chelo" / "agents", ["viejo"])

        self.assertEqual(self._locate(), legacy)

    def test_nothing_found_is_none_not_an_error(self):
        self.assertIsNone(self._locate())
        self.assertEqual(self._roles_found(), [])


class TestSingleImplementation(unittest.TestCase):
    """CLI y MCP deben resolver al mismo lugar: una sola implementación."""

    def test_mcp_delegates_to_the_shared_lookup(self):
        """Si el MCP vuelve a tener su propia lista, este test falla."""
        from unittest import mock

        from lib.mcp import runtime

        sentinel = Path("/ruta/compartida/agents")
        with mock.patch("lib.core.resources.agents_dir", return_value=sentinel) as shared:
            self.assertEqual(runtime.agents_dir(), sentinel)
        shared.assert_called_once()

    def test_cli_delegates_to_the_shared_lookup(self):
        """Idem para la CLI: los roles salen de `lib.core.resources`."""
        from unittest import mock

        from lib.orchestration import cli

        self.assertIs(cli.available_roles, resources.available_roles)


if __name__ == "__main__":
    unittest.main()
