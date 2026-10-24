#!/usr/bin/env python3
"""
Regresión de la detección de stack (`lib/core/stack_detector.py`).

Este módulo alimenta el mensaje de arranque de cada sesión, así que lo que fija
este archivo es qué se reconoce y con qué prioridad:

1. Contrato y pruebas: `openapi.yaml`, `openapi.yml` y `api*.yaml` en cualquier
   subdirectorio; cualquier `*.hurl`; `Dockerfile` o `docker-compose.yml` en la
   raíz.
2. Node: el gestor de paquetes sale del lockfile y el framework del contenido de
   `package.json`. Next.js gana sobre React porque lo incluye.
3. Python, Go y Rust: se reconocen por su manifiesto y el último gana, porque el
   dict tiene un solo campo `backend`.
4. Un directorio vacío no inventa nada.

El último grupo es el que de verdad importa: **el detector y el motor de mocks
tienen que contestar lo mismo** cuando se les pregunta si hay contrato. Hoy no
lo hacen con `api-v1.yaml`: el detector dice que no hay y `mock` lo encuentra.
"""

import unittest
from pathlib import Path
import os
import tempfile

from lib.core.stack_detector import detect_workspace_stack
from lib.spec.mock_engine import find_openapi_spec


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        self._cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self._cwd)

    def touch(self, relative, body=""):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def detect(self):
        return detect_workspace_stack()


class ContractAndTools(Base):

    def test_openapi_yaml_is_found_at_the_root(self):
        self.touch("openapi.yaml", "openapi: 3.0.0\n")
        self.assertTrue(self.detect()["has_openapi"])

    def test_openapi_yml_is_found(self):
        self.touch("openapi.yml", "openapi: 3.0.0\n")
        self.assertTrue(self.detect()["has_openapi"])

    def test_the_contract_may_live_in_a_subdirectory(self):
        self.touch("docs/openapi.yaml", "openapi: 3.0.0\n")
        self.assertTrue(self.detect()["has_openapi"])

    def test_an_api_named_contract_is_found(self):
        self.touch("api.yaml", "openapi: 3.0.0\n")
        self.assertTrue(self.detect()["has_openapi"])

    def test_a_suffixed_api_contract_is_found(self):
        """`api-v1.yaml` es un contrato válido y el mock lo levanta."""
        self.touch("api-v1.yaml", "openapi: 3.0.0\n")
        self.assertTrue(self.detect()["has_openapi"])

    def test_without_a_contract_it_says_no(self):
        self.touch("README.md", "# proyecto\n")
        self.assertFalse(self.detect()["has_openapi"])

    def test_a_hurl_test_is_found_in_a_subdirectory(self):
        self.touch("tests/000_health.hurl", "GET http://localhost:4010/health\n")
        self.assertTrue(self.detect()["has_hurl"])

    def test_without_hurl_tests_it_says_no(self):
        self.assertFalse(self.detect()["has_hurl"])

    def test_a_dockerfile_is_found_at_the_root(self):
        self.touch("Dockerfile", "FROM python:3.12\n")
        self.assertTrue(self.detect()["has_docker"])

    def test_docker_compose_is_found(self):
        self.touch("docker-compose.yml", "services: {}\n")
        self.assertTrue(self.detect()["has_docker"])

    def test_without_docker_it_says_no(self):
        self.assertFalse(self.detect()["has_docker"])


class Node(Base):

    def package(self, body):
        return self.touch("package.json", body)

    def test_package_json_defaults_to_npm(self):
        self.package('{"name": "x"}')
        self.assertEqual(self.detect()["package_manager"], "npm")

    def test_pnpm_lock_wins(self):
        self.package('{"name": "x"}')
        self.touch("pnpm-lock.yaml")
        self.assertEqual(self.detect()["package_manager"], "pnpm")

    def test_yarn_lock_is_recognized(self):
        self.package('{"name": "x"}')
        self.touch("yarn.lock")
        self.assertEqual(self.detect()["package_manager"], "yarn")

    def test_bun_binary_lock_is_recognized(self):
        self.package('{"name": "x"}')
        self.touch("bun.lockb")
        self.assertEqual(self.detect()["package_manager"], "bun")

    def test_bun_text_lock_is_recognized(self):
        self.package('{"name": "x"}')
        self.touch("bun.lock")
        self.assertEqual(self.detect()["package_manager"], "bun")

    def test_a_lockfile_without_package_json_is_not_a_node_project(self):
        self.touch("pnpm-lock.yaml")
        self.assertIsNone(self.detect()["package_manager"])

    def test_next_is_detected_as_frontend(self):
        self.package('{"dependencies": {"next": "14.0.0"}}')
        self.assertEqual(self.detect()["frontend"], "Next.js")

    def test_react_is_detected_as_frontend(self):
        self.package('{"dependencies": {"react": "18.0.0"}}')
        self.assertEqual(self.detect()["frontend"], "React")

    def test_vue_is_detected_as_frontend(self):
        self.package('{"dependencies": {"vue": "3.0.0"}}')
        self.assertEqual(self.detect()["frontend"], "Vue")

    def test_next_wins_over_react_because_it_includes_it(self):
        self.package('{"dependencies": {"next": "14.0.0", "react": "18.0.0"}}')
        self.assertEqual(self.detect()["frontend"], "Next.js")

    def test_express_is_detected_as_backend(self):
        self.package('{"dependencies": {"express": "4.0.0"}}')
        self.assertEqual(self.detect()["backend"], "Node.js (Express/Fastify/Nest)")

    def test_fastify_is_detected_as_backend(self):
        self.package('{"dependencies": {"fastify": "4.0.0"}}')
        self.assertEqual(self.detect()["backend"], "Node.js (Express/Fastify/Nest)")


class PythonGoRust(Base):

    def test_requirements_txt_is_python(self):
        self.touch("requirements.txt", "fastapi\n")
        self.assertEqual(self.detect()["backend"], "Python (FastAPI/Flask/Django)")

    def test_pyproject_is_python_with_poetry_or_pip(self):
        self.touch("pyproject.toml", "[project]\nname = 'x'\n")
        stack = self.detect()

        self.assertEqual(stack["backend"], "Python (FastAPI/Flask/Django)")
        self.assertEqual(stack["package_manager"], "poetry/pip")

    def test_pipfile_is_python(self):
        self.touch("Pipfile", "[[source]]\n")
        self.assertEqual(self.detect()["backend"], "Python (FastAPI/Flask/Django)")

    def test_go_mod_is_go(self):
        self.touch("go.mod", "module x\n")
        self.assertEqual(self.detect()["backend"], "Go")

    def test_cargo_toml_is_rust(self):
        self.touch("Cargo.toml", "[package]\nname = 'x'\n")
        self.assertEqual(self.detect()["backend"], "Rust")

    def test_rust_wins_over_go_and_python(self):
        """El dict tiene un solo `backend`: el último manifiesto gana."""
        self.touch("requirements.txt", "fastapi\n")
        self.touch("go.mod", "module x\n")
        self.touch("Cargo.toml", "[package]\n")

        self.assertEqual(self.detect()["backend"], "Rust")


class Defaults(Base):

    def test_an_empty_directory_reports_nothing(self):
        self.assertEqual(
            self.detect(),
            {
                "backend": None,
                "frontend": None,
                "package_manager": None,
                "has_openapi": False,
                "has_hurl": False,
                "has_docker": False,
            },
        )

    def test_the_root_can_be_passed_explicitly(self):
        elsewhere = self.root / "otro"
        elsewhere.mkdir()
        (elsewhere / "go.mod").write_text("module x\n", encoding="utf-8")

        self.assertEqual(detect_workspace_stack(elsewhere)["backend"], "Go")
        self.assertIsNone(self.detect()["backend"])

    def test_the_contract_is_searched_under_the_given_root(self):
        """Sin esto, pasar el root no sirve de nada para el contrato."""
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        elsewhere = Path(outside.name)
        (elsewhere / "openapi.yaml").write_text("openapi: 3.0.0\n", encoding="utf-8")

        # La búsqueda es recursiva desde el cwd: el otro root tiene que quedar
        # afuera de este árbol para que la prueba signifique algo.
        self.assertFalse(self.detect()["has_openapi"])
        self.assertTrue(detect_workspace_stack(elsewhere)["has_openapi"])


class ContractConsistency(Base):
    """
    Detector y motor de mocks contestan la misma pregunta: ¿hay contrato acá?

    Si discrepan, la sesión dice "no encontrado (se creará con 'init')" y dos
    segundos después `mock` levanta Prism con el archivo que sí estaba.
    """

    LAYOUTS = (
        (),
        ("openapi.yaml",),
        ("openapi.yml",),
        ("docs/openapi.yaml",),
        ("api.yaml",),
        ("api-v1.yaml",),
        ("api.yml",),
    )

    def test_both_modules_agree_on_every_layout(self):
        for layout in self.LAYOUTS:
            with self.subTest(layout=layout or ("vacío",)):
                for leftover in list(self.root.glob("**/*.y*ml")):
                    leftover.unlink()
                for name in layout:
                    self.touch(name, "openapi: 3.0.0\n")

                detected = self.detect()["has_openapi"]
                found = find_openapi_spec() is not None

                self.assertEqual(
                    detected,
                    found,
                    f"detector={detected} mock={found} para {layout or ('vacío',)}",
                )


if __name__ == "__main__":
    unittest.main()
