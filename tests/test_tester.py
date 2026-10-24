#!/usr/bin/env python3
"""
Regresión del ejecutor de contrato (`lib/spec/tester.py`).

Es la pieza que levanta el mock y corre los tests, así que lo que fija este
archivo son las decisiones que afectan al usuario:

1. Qué binario de hurl se usa (PATH primero, ~/.local/bin después) y qué pasa
   cuando no hay ninguno: cae a un ejecutor nativo que sólo compara el status.
2. Sin archivos .hurl se falla explícito, no se reporta un éxito vacío.
3. Un test que falla devuelve el stderr del error, no un mensaje genérico.
4. El mock se levanta sólo si el puerto está cerrado y hay spec más runner.
5. El mock que levanta esta función se termina siempre — también cuando un
   test lanza una excepción. Un Prism huérfano se queda con el puerto y hace
   fallar la próxima corrida con un error que no tiene nada que ver.
"""

import io
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from lib.spec import tester


class FakeSocket:
    def __init__(self, connect_result):
        self.connect_result = connect_result

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def settimeout(self, value):
        pass

    def connect_ex(self, address):
        return self.connect_result


class FakeResponse:
    def __init__(self, code):
        self.code = code

    def getcode(self):
        return self.code

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Base(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self._cwd = Path.cwd()
        import os

        os.chdir(self.root)
        self.addCleanup(os.chdir, self._cwd)

        patcher = mock.patch.object(tester.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def hurl(self, name="001.hurl", body="GET http://localhost:4010/x\nHTTP 200\n"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def port(self, is_open):
        """Simula el puerto de Prism abierto o cerrado."""
        patcher = mock.patch.object(
            tester.socket, "socket", lambda *a, **k: FakeSocket(0 if is_open else 1)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def mock_process(self):
        proc = mock.Mock()
        proc.terminate = mock.Mock()
        proc.wait = mock.Mock()
        proc.kill = mock.Mock()
        return proc


class FindHurlRunner(Base):

    def test_prefers_the_binary_in_path(self):
        with mock.patch.object(tester.shutil, "which", return_value="/usr/bin/hurl"):
            self.assertEqual(tester.find_hurl_runner(), "hurl")

    def test_falls_back_to_the_user_binary(self):
        local_bin = self.root / ".local" / "bin"
        local_bin.mkdir(parents=True)
        binary = local_bin / "hurl"
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
        binary.chmod(0o755)

        with mock.patch.object(tester.shutil, "which", return_value=None), \
                mock.patch.object(tester.Path, "home", return_value=self.root):
            self.assertEqual(tester.find_hurl_runner(), str(binary))

    def test_none_when_there_is_no_hurl(self):
        with mock.patch.object(tester.shutil, "which", return_value=None), \
                mock.patch.object(tester.Path, "home", return_value=self.root):
            self.assertIsNone(tester.find_hurl_runner())


class NativeFallback(Base):

    def test_a_file_with_only_comments_passes(self):
        path = self.hurl(body="# nada que ejecutar\n\n")
        self.assertTrue(tester.run_native_python_test(path))

    def test_matching_status_passes(self):
        path = self.hurl(body="GET http://localhost:4010/x\nHTTP 200\n")
        with mock.patch.object(urllib.request, "urlopen", return_value=FakeResponse(200)):
            self.assertTrue(tester.run_native_python_test(path))

    def test_mismatched_status_fails(self):
        path = self.hurl(body="GET http://localhost:4010/x\nHTTP 200\n")
        with mock.patch.object(urllib.request, "urlopen", return_value=FakeResponse(500)):
            self.assertFalse(tester.run_native_python_test(path))

    def test_http_error_uses_its_status_code(self):
        path = self.hurl(body="GET http://localhost:4010/x\nHTTP 404\n")
        error = urllib.error.HTTPError("http://localhost:4010/x", 404, "no", None, None)
        with mock.patch.object(urllib.request, "urlopen", side_effect=error):
            self.assertTrue(tester.run_native_python_test(path))

    def test_unreachable_server_fails(self):
        path = self.hurl(body="GET http://localhost:4010/x\nHTTP 200\n")
        with mock.patch.object(
            urllib.request, "urlopen", side_effect=urllib.error.URLError("sin red")
        ):
            self.assertFalse(tester.run_native_python_test(path))


class ExecuteTests(Base):

    def _run(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = tester.execute_tests_and_collect_errors()
        return result, buffer.getvalue()

    def test_without_hurl_files_it_fails_explicitly(self):
        (passed, errors), _ = self._run()

        self.assertFalse(passed)
        self.assertEqual(len(errors), 1)
        self.assertIn("No se encontraron archivos", errors[0])

    def test_a_passing_test_reports_success(self):
        self.hurl()
        self.port(is_open=True)
        ok = mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(tester, "find_hurl_runner", return_value="hurl"), \
                mock.patch.object(tester.subprocess, "run", return_value=ok):
            (passed, errors), output = self._run()

        self.assertTrue(passed)
        self.assertEqual(errors, [])
        self.assertIn("PASÓ", output)

    def test_a_failing_test_returns_the_stderr(self):
        self.hurl()
        self.port(is_open=True)
        bad = mock.Mock(returncode=1, stdout="", stderr="error: assert status code")

        with mock.patch.object(tester, "find_hurl_runner", return_value="hurl"), \
                mock.patch.object(tester.subprocess, "run", return_value=bad):
            (passed, errors), output = self._run()

        self.assertFalse(passed)
        self.assertIn("assert status code", errors[0])
        self.assertIn("FALLÓ", output)

    def test_the_loader_warning_is_filtered_from_the_report(self):
        self.hurl()
        self.port(is_open=True)
        bad = mock.Mock(
            returncode=1,
            stdout="",
            stderr="hurl: /lib/libssl.so: no version information available\nreal error",
        )

        with mock.patch.object(tester, "find_hurl_runner", return_value="hurl"), \
                mock.patch.object(tester.subprocess, "run", return_value=bad):
            (_, errors), _ = self._run()

        self.assertNotIn("no version information available", errors[0])
        self.assertIn("real error", errors[0])

    def test_it_starts_the_mock_when_the_port_is_closed(self):
        self.hurl()
        self.port(is_open=False)
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        spec = self.root / "openapi.yaml"
        spec.write_text("openapi: 3.0.0\n", encoding="utf-8")

        with mock.patch.object(tester, "find_hurl_runner", return_value="hurl"), \
                mock.patch.object(tester, "find_openapi_spec", return_value=spec), \
                mock.patch.object(tester, "find_prism_runner", return_value=["prism"]), \
                mock.patch.object(tester.subprocess, "Popen", return_value=self.mock_process()) as popen, \
                mock.patch.object(tester.subprocess, "run", return_value=ok):
            self._run()

        popen.assert_called_once()
        command = popen.call_args.args[0]
        self.assertEqual(command[:2], ["prism", "mock"])
        self.assertIn(str(spec), command)

    def test_it_does_not_start_a_second_mock_when_the_port_is_open(self):
        self.hurl()
        self.port(is_open=True)
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        spec = self.root / "openapi.yaml"
        spec.write_text("openapi: 3.0.0\n", encoding="utf-8")

        # Spec y runner disponibles: lo único que impide levantar otro mock es
        # que el puerto ya responde.
        with mock.patch.object(tester, "find_hurl_runner", return_value="hurl"), \
                mock.patch.object(tester, "find_openapi_spec", return_value=spec), \
                mock.patch.object(tester, "find_prism_runner", return_value=["prism"]), \
                mock.patch.object(tester.subprocess, "Popen") as popen, \
                mock.patch.object(tester.subprocess, "run", return_value=ok):
            self._run()

        popen.assert_not_called()

    def test_it_terminates_the_mock_it_started(self):
        self.hurl()
        self.port(is_open=False)
        proc = self.mock_process()
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        spec = self.root / "openapi.yaml"
        spec.write_text("openapi: 3.0.0\n", encoding="utf-8")

        with mock.patch.object(tester, "find_hurl_runner", return_value="hurl"), \
                mock.patch.object(tester, "find_openapi_spec", return_value=spec), \
                mock.patch.object(tester, "find_prism_runner", return_value=["prism"]), \
                mock.patch.object(tester.subprocess, "Popen", return_value=proc), \
                mock.patch.object(tester.subprocess, "run", return_value=ok):
            self._run()

        proc.terminate.assert_called_once()

    def test_it_terminates_the_mock_even_when_a_test_raises(self):
        """Un Prism huérfano se queda con el puerto y rompe la corrida siguiente."""
        self.hurl()
        self.port(is_open=False)
        proc = self.mock_process()
        spec = self.root / "openapi.yaml"
        spec.write_text("openapi: 3.0.0\n", encoding="utf-8")

        with mock.patch.object(tester, "find_hurl_runner", return_value="hurl"), \
                mock.patch.object(tester, "find_openapi_spec", return_value=spec), \
                mock.patch.object(tester, "find_prism_runner", return_value=["prism"]), \
                mock.patch.object(tester.subprocess, "Popen", return_value=proc), \
                mock.patch.object(tester.subprocess, "run", side_effect=OSError("hurl desapareció")):
            with self.assertRaises(OSError):
                self._run()

        proc.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
