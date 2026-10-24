#!/usr/bin/env python3
"""
Regresión del motor de mocks (`lib/spec/mock_engine.py`).

Cubre las dos mitades del módulo:

1. Detección: qué spec se elige y qué runner de Prism se prefiere (local,
   PATH, npx con versión fijada, o ninguno).
2. El mock nativo de Python: lectura del OpenAPI y respuesta por método y
   ruta. El servidor en sí no se levanta; lo que se prueba son las dos
   funciones puras que lo alimentan, que es donde vive la decisión.

El orden de las respuestas también se fija: `/health` gana sobre el 201 de
POST, porque así se comportaba antes de separar el código.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.spec import mock_engine


def _result(stdout="", returncode=0):
    return mock.Mock(returncode=returncode, stdout=stdout, stderr="")


class FindOpenApiSpec(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        import os

        self._cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self._cwd)

    def touch(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("openapi: 3.0.0\n", encoding="utf-8")
        return path

    def test_it_finds_openapi_yaml(self):
        expected = self.touch("openapi.yaml")
        self.assertEqual(mock_engine.find_openapi_spec(), expected)

    def test_it_finds_the_yml_variant(self):
        expected = self.touch("openapi.yml")
        self.assertEqual(mock_engine.find_openapi_spec(), expected)

    def test_it_finds_api_named_files(self):
        expected = self.touch("docs/api-v1.yaml")
        self.assertEqual(mock_engine.find_openapi_spec(), expected)

    def test_yaml_wins_over_the_yml_variant(self):
        preferred = self.touch("openapi.yaml")
        self.touch("openapi.yml")
        self.assertEqual(mock_engine.find_openapi_spec(), preferred)

    def test_without_a_spec_it_returns_none(self):
        self.assertIsNone(mock_engine.find_openapi_spec())

    def test_it_searches_the_root_it_is_given(self):
        """El detector de stack le pasa un root; si se ignora, miente."""
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        elsewhere = Path(outside.name)
        expected = elsewhere / "api-v2.yaml"
        expected.write_text("openapi: 3.0.0\n", encoding="utf-8")

        self.assertIsNone(mock_engine.find_openapi_spec())
        self.assertEqual(mock_engine.find_openapi_spec(elsewhere), expected)


class FindPrismRunner(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        import os

        self._cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self._cwd)

    def test_the_local_binary_wins(self):
        binary = self.root / "node_modules" / ".bin" / "prism"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        binary.chmod(0o755)

        with mock.patch.object(mock_engine.shutil, "which", return_value="/usr/bin/prism"):
            self.assertEqual(mock_engine.find_prism_runner(), [str(binary)])

    def test_a_non_executable_local_file_is_ignored(self):
        binary = self.root / "node_modules" / ".bin" / "prism"
        binary.parent.mkdir(parents=True)
        binary.write_text("no ejecutable", encoding="utf-8")
        binary.chmod(0o644)

        with mock.patch.object(mock_engine.shutil, "which", side_effect=lambda name: "/usr/bin/prism" if name == "prism" else None):
            self.assertEqual(mock_engine.find_prism_runner(), ["prism"])

    def test_the_path_binary_is_the_second_choice(self):
        with mock.patch.object(mock_engine.shutil, "which", side_effect=lambda name: "/usr/bin/prism" if name == "prism" else None):
            self.assertEqual(mock_engine.find_prism_runner(), ["prism"])

    def test_npx_is_the_last_resort_and_pins_the_major(self):
        with mock.patch.object(mock_engine.shutil, "which", side_effect=lambda name: "/usr/bin/npx" if name == "npx" else None):
            self.assertEqual(
                mock_engine.find_prism_runner(), ["npx", "--yes", "@stoplight/prism-cli@5"]
            )

    def test_without_anything_it_returns_none(self):
        with mock.patch.object(mock_engine.shutil, "which", return_value=None):
            self.assertIsNone(mock_engine.find_prism_runner())


class ParseEndpoints(unittest.TestCase):

    SPEC = """openapi: 3.0.0
paths:
  /health:
    get:
      responses:
        '200':
          description: ok
  /users:
    get:
      responses: {}
    post:
      responses: {}
  /users/{id}:
    delete:
      responses: {}
"""

    def test_it_reads_paths_and_methods(self):
        parsed = mock_engine.parse_endpoints(self.SPEC)

        self.assertEqual(sorted(parsed), ["/health", "/users", "/users/{id}"])
        self.assertEqual(sorted(parsed["/users"]), ["GET", "POST"])
        self.assertIn("DELETE", parsed["/users/{id}"])

    def test_every_endpoint_answers_200_ok(self):
        parsed = mock_engine.parse_endpoints(self.SPEC)

        self.assertEqual(parsed["/health"]["GET"], {"status": 200, "body": {"status": "ok", "mock": "python-native"}})

    def test_non_method_keys_are_ignored(self):
        parsed = mock_engine.parse_endpoints(self.SPEC)

        self.assertNotIn("responses", parsed["/users"])
        self.assertNotIn("RESPONSES", parsed["/users"])

    def test_an_empty_document_has_no_endpoints(self):
        self.assertEqual(mock_engine.parse_endpoints(""), {})


class BuildResponse(unittest.TestCase):

    ENDPOINTS = {"/users": {"GET": {"status": 200, "body": {"users": []}}}}

    def test_health_answers_healthy(self):
        status, body = mock_engine.build_response(self.ENDPOINTS, "GET", "/health")

        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "healthy", "service": "chelo-harness-mock"})

    def test_api_health_answers_healthy(self):
        status, body = mock_engine.build_response(self.ENDPOINTS, "GET", "/api/health")

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "healthy")

    def test_health_wins_over_the_post_status(self):
        status, _ = mock_engine.build_response(self.ENDPOINTS, "POST", "/health")

        self.assertEqual(status, 200)

    def test_post_answers_created(self):
        status, body = mock_engine.build_response(self.ENDPOINTS, "POST", "/users")

        self.assertEqual(status, 201)
        self.assertEqual(body["status"], "created")
        self.assertEqual(body["path"], "/users")

    def test_a_declared_endpoint_uses_its_body(self):
        status, body = mock_engine.build_response(self.ENDPOINTS, "GET", "/users")

        self.assertEqual(status, 200)
        self.assertEqual(body, {"users": []})

    def test_a_declared_path_with_another_method_falls_back(self):
        status, body = mock_engine.build_response(self.ENDPOINTS, "DELETE", "/users")

        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")
        self.assertIn("DELETE /users", body["message"])

    def test_the_query_string_is_ignored(self):
        status, body = mock_engine.build_response(self.ENDPOINTS, "GET", "/users?page=2")

        self.assertEqual(status, 200)
        self.assertEqual(body, {"users": []})

    def test_an_unknown_path_answers_200_with_a_message(self):
        status, body = mock_engine.build_response(self.ENDPOINTS, "GET", "/nope")

        self.assertEqual(status, 200)
        self.assertIn("GET /nope", body["message"])


class CommandMock(unittest.TestCase):

    def _run(self, spec, runner):
        with mock.patch.object(mock_engine, "banner"), \
                mock.patch.object(mock_engine, "find_openapi_spec", return_value=spec), \
                mock.patch.object(mock_engine, "find_prism_runner", return_value=runner), \
                mock.patch.object(mock_engine.subprocess, "run") as run, \
                mock.patch.object(mock_engine, "run_native_python_mock") as native:
            buffer = mock.patch("builtins.print")
            with buffer:
                code = None
                try:
                    mock_engine.cmd_mock()
                except SystemExit as exc:
                    code = exc.code
        return code, run, native

    def test_without_a_spec_it_exits_with_one(self):
        code, run, _ = self._run(None, None)

        self.assertEqual(code, 1)
        run.assert_not_called()

    def test_it_runs_prism_when_available(self):
        spec = Path("/repo/openapi.yaml")
        code, run, native = self._run(spec, ["prism"])

        self.assertIsNone(code)
        run.assert_called_once_with(
            ["prism", "mock", str(spec), "-p", str(mock_engine.PRISM_PORT)]
        )
        native.assert_not_called()

    def test_it_falls_back_to_the_native_mock(self):
        spec = Path("/repo/openapi.yaml")
        _, run, native = self._run(spec, None)

        run.assert_not_called()
        native.assert_called_once_with(spec, mock_engine.PRISM_PORT)


class CommandProxy(unittest.TestCase):

    def _run(self, spec, runner):
        with mock.patch.object(mock_engine, "banner"), \
                mock.patch.object(mock_engine, "find_openapi_spec", return_value=spec), \
                mock.patch.object(mock_engine, "find_prism_runner", return_value=runner), \
                mock.patch.object(mock_engine.subprocess, "run") as run, \
                mock.patch("builtins.print"):
            code = None
            try:
                mock_engine.cmd_proxy("http://localhost:9000")
            except SystemExit as exc:
                code = exc.code
        return code, run

    def test_without_a_spec_it_exits_with_one(self):
        code, run = self._run(None, None)

        self.assertEqual(code, 1)
        run.assert_not_called()

    def test_it_validates_against_the_backend(self):
        spec = Path("/repo/openapi.yaml")
        _, run = self._run(spec, ["prism"])

        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["prism", "proxy", str(spec)])
        self.assertIn("http://localhost:9000", command)
        self.assertIn("--validate-request", command)

    def test_without_prism_it_does_not_pretend_to_proxy(self):
        spec = Path("/repo/openapi.yaml")
        code, run = self._run(spec, None)

        self.assertIsNone(code)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
