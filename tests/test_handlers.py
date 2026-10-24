#!/usr/bin/env python3
"""
Tests de los handlers del MCP (`lib/mcp/handlers/`).

Cubren las seis familias — gobernanza, contrato, mock, workspace, canales y
agentes — sin red, sin API keys y sin procesos reales. Cada handler se invoca
con lo que recibe del protocolo (un dict de argumentos) y se verifica el
payload exacto que devuelve, que es el contrato que consume el cliente.

Trampa que estos tests fijan: el shell del desarrollador puede tener claves de
proveedor reales cargadas. Todas se limpian en `setUp` para que ningún handler
lea el entorno real.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.mcp.handlers import agents as agents_handler
from lib.mcp.handlers import channels as channels_handler
from lib.mcp.handlers import contract as contract_handler
from lib.mcp.handlers import governance as governance_handler
from lib.mcp.handlers import mock as mock_handler
from lib.mcp.handlers import workspace as workspace_handler

ENV_KEYS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "SLACK_WEBHOOK_URL",
    "SLACK_BOT_TOKEN",
    "SLACK_USER_TOKEN",
)


class HandlerTestCase(unittest.TestCase):
    """Aísla cwd y entorno: los handlers operan sobre el proceso."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self._previous_cwd = Path.cwd()
        os.chdir(self.root)

        environ = mock.patch.dict(os.environ, {}, clear=False)
        environ.start()
        self.addCleanup(environ.stop)
        for key in ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        os.chdir(self._previous_cwd)
        self._tmp.cleanup()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# Contrato: parser de endpoints y lectura del OpenAPI
# ---------------------------------------------------------------------------
class TestParseOpenapiPaths(unittest.TestCase):

    SAMPLE = """\
openapi: 3.0.0
info:
  title: Demo
paths:
  /health:
    get:
      summary: health
      responses:
        '200':
          description: ok
  /games:
    GET:
      summary: list
    post:
      summary: create
    parameters:
      - name: id
components:
  schemas:
    Game:
      type: object
"""

    def test_lists_paths_with_their_methods(self):
        paths = contract_handler.parse_openapi_paths(self.SAMPLE)
        self.assertEqual(paths["/health"], ["GET"])
        self.assertEqual(paths["/games"], ["GET", "POST"])

    def test_ignores_nested_and_foreign_blocks(self):
        paths = contract_handler.parse_openapi_paths(self.SAMPLE)
        self.assertEqual(set(paths), {"/health", "/games"})
        self.assertNotIn("components", paths)

    def test_tolerates_comments_blank_lines_and_lowercase_methods(self):
        text = (
            "# un comentario\n"
            "\n"
            "paths:\n"
            "  /ping:\n"
            "    delete:\n"
            "      summary: x\n"
        )
        self.assertEqual(contract_handler.parse_openapi_paths(text), {"/ping": ["DELETE"]})

    def test_empty_document_yields_no_paths(self):
        self.assertEqual(contract_handler.parse_openapi_paths(""), {})
        self.assertEqual(contract_handler.parse_openapi_paths("openapi: 3.0.0\n"), {})

    def test_a_non_path_key_at_path_level_closes_the_block(self):
        """Los métodos de un bloque ajeno no pueden filtrarse al path anterior."""
        text = (
            "paths:\n"
            "  /a:\n"
            "    get:\n"
            "  junk:\n"
            "    post:\n"
        )
        self.assertEqual(contract_handler.parse_openapi_paths(text), {"/a": ["GET"]})


class TestSpecPath(unittest.TestCase):

    def setUp(self):
        self.root = Path("/work/repo")

    def test_relative_path_is_resolved_against_the_workspace(self):
        self.assertEqual(contract_handler._spec_path("docs/openapi.yaml", self.root),
                         Path("/work/repo/docs/openapi.yaml"))

    def test_absolute_path_inside_the_workspace_is_accepted(self):
        self.assertEqual(contract_handler._spec_path("/work/repo/openapi.yml", self.root),
                         Path("/work/repo/openapi.yml"))

    def test_absolute_path_outside_the_workspace_is_rejected(self):
        self.assertIsNone(contract_handler._spec_path("/etc/openapi.yaml", self.root))
        self.assertIsNone(contract_handler._spec_path("/work/repo/../otro/openapi.yaml", self.root))

    def test_sibling_directory_with_shared_prefix_is_rejected(self):
        self.assertIsNone(contract_handler._spec_path("/work/repository/openapi.yaml", self.root))


class TestSpecRead(HandlerTestCase):

    def test_reports_missing_contract(self):
        with mock.patch("lib.spec.mock_engine.find_openapi_spec", return_value=None):
            result = contract_handler.h_spec_read({})
        self.assertFalse(result["found"])
        self.assertIn("chelo_init", result["error"])

    def test_reads_detected_contract_without_content_by_default(self):
        spec = self.write("openapi.yaml", "paths:\n  /health:\n    get:\n      summary: ok\n")
        with mock.patch("lib.spec.mock_engine.find_openapi_spec", return_value=spec):
            result = contract_handler.h_spec_read({})

        self.assertTrue(result["found"])
        self.assertEqual(result["path"], str(spec))
        self.assertEqual(result["bytes"], len(spec.read_text(encoding="utf-8")))
        self.assertEqual(result["endpoints"], {"/health": ["GET"]})
        self.assertIsNone(result["content"])

    def test_includes_full_yaml_only_when_asked(self):
        spec = self.write("api/openapi.yml", "paths: {}\n")
        with mock.patch("lib.spec.mock_engine.find_openapi_spec", return_value=spec):
            result = contract_handler.h_spec_read({"include_content": True})
        self.assertEqual(result["content"], "paths: {}\n")

    def test_rejects_explicit_path_outside_the_workspace(self):
        result = contract_handler.h_spec_read({"path": "/etc/openapi.yaml"})
        self.assertFalse(result["found"])
        self.assertIn("fuera del workspace", result["error"])

    def test_reports_nonexistent_file_inside_the_workspace(self):
        result = contract_handler.h_spec_read({"path": "no-existe.yaml"})
        self.assertFalse(result["found"])
        self.assertIn("inexistente", result["error"])

    def test_explicit_relative_path_wins_over_detection(self):
        spec = self.write("contracts/mine.yaml", "paths:\n  /x:\n    put:\n")
        with mock.patch("lib.spec.mock_engine.find_openapi_spec", return_value=None):
            result = contract_handler.h_spec_read({"path": "contracts/mine.yaml"})
        self.assertTrue(result["found"])
        self.assertEqual(result["endpoints"], {"/x": ["PUT"]})


class TestContractTest(HandlerTestCase):

    def test_returns_passing_suite(self):
        with mock.patch("lib.spec.tester.execute_tests_and_collect_errors", return_value=(True, [])):
            result = contract_handler.h_contract_test({})
        self.assertEqual(result, {"passed": True, "errors": [], "log": ""})

    def test_returns_failures_and_captured_log(self):
        def failing():
            print("corriendo hurl")
            return False, ["GET /health esperaba 200"]

        with mock.patch("lib.spec.tester.execute_tests_and_collect_errors", side_effect=failing):
            result = contract_handler.h_contract_test({})

        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"], ["GET /health esperaba 200"])
        self.assertEqual(result["log"], "corriendo hurl")

    def test_exception_becomes_an_error_payload(self):
        with mock.patch("lib.spec.tester.execute_tests_and_collect_errors",
                        side_effect=RuntimeError("hurl explotó")):
            result = contract_handler.h_contract_test({})

        self.assertFalse(result["passed"])
        self.assertEqual(result["error"], "RuntimeError: hurl explotó")

    def test_system_exit_becomes_an_error_payload(self):
        with mock.patch("lib.spec.tester.execute_tests_and_collect_errors", side_effect=SystemExit(3)):
            result = contract_handler.h_contract_test({})

        self.assertFalse(result["passed"])
        self.assertIn("código 3", result["error"])


# ---------------------------------------------------------------------------
# Gobernanza
# ---------------------------------------------------------------------------
class GovernanceTestCase(HandlerTestCase):

    def patch_gate(self, count, files=None, limit=10):
        return [
            mock.patch("lib.core.gate.get_git_status", return_value=(count, files or [])),
            mock.patch("lib.core.gate.MAX_ALLOWED_CHANGES", limit),
        ]


class TestStatus(GovernanceTestCase):

    def test_reports_full_workspace_state_inside_a_git_repo(self):
        spec = self.write("openapi.yaml", "paths: {}\n")
        self.write("tests/health.hurl", "GET http://localhost:4010/health\n")
        self.write("tests/nested/deep.hurl", "GET http://localhost:4010/x\n")

        git = mock.Mock(returncode=0, stdout="true\n", stderr="")
        patches = self.patch_gate(3, [" M a.py", " M b.py", "?? c.py"])
        with patches[0], patches[1], \
                mock.patch.object(governance_handler.subprocess, "run", return_value=git), \
                mock.patch("lib.core.stack_detector.detect_workspace_stack", return_value={"backend": "python"}), \
                mock.patch("lib.spec.mock_engine.find_openapi_spec", return_value=spec), \
                mock.patch.object(governance_handler, "port_open", return_value=True):
            result = governance_handler.h_status({})

        self.assertEqual(result["workspace"], str(self.root))
        self.assertEqual(result["project"], self.root.name)
        self.assertTrue(result["is_git_repo"])
        self.assertEqual(result["modified_files"], 3)
        self.assertEqual(result["limit"], 10)
        self.assertTrue(result["within_limit"])
        self.assertEqual(result["files"], [" M a.py", " M b.py", "?? c.py"])
        self.assertEqual(result["spec"], "openapi.yaml")
        self.assertEqual(result["contract_tests"], ["tests/health.hurl", "tests/nested/deep.hurl"])
        self.assertTrue(result["mock_running"])
        self.assertEqual(result["stack"], {"backend": "python"})

    def test_non_git_workspace_reports_zero_changes_and_no_contract(self):
        git = mock.Mock(returncode=128, stdout="", stderr="fatal")
        with mock.patch.object(governance_handler.subprocess, "run", return_value=git), \
                mock.patch("lib.core.stack_detector.detect_workspace_stack", return_value={}), \
                mock.patch("lib.spec.mock_engine.find_openapi_spec", return_value=None), \
                mock.patch.object(governance_handler, "port_open", return_value=False):
            result = governance_handler.h_status({})

        self.assertFalse(result["is_git_repo"])
        self.assertEqual(result["modified_files"], 0)
        self.assertEqual(result["files"], [])
        self.assertIsNone(result["spec"])
        self.assertEqual(result["contract_tests"], [])
        self.assertFalse(result["mock_running"])

    def test_over_limit_workspace_reports_within_limit_false(self):
        git = mock.Mock(returncode=0)
        patches = self.patch_gate(11, limit=10)
        with patches[0], patches[1], \
                mock.patch.object(governance_handler.subprocess, "run", return_value=git), \
                mock.patch("lib.core.stack_detector.detect_workspace_stack", return_value={}), \
                mock.patch("lib.spec.mock_engine.find_openapi_spec", return_value=None), \
                mock.patch.object(governance_handler, "port_open", return_value=False):
            result = governance_handler.h_status({})
        self.assertFalse(result["within_limit"])


class TestAuditChanges(GovernanceTestCase):

    def test_flags_safe_workspace(self):
        with self.patch_gate(4)[0]:
            result = governance_handler.h_audit_changes({})
        self.assertTrue(result["is_safe"])
        self.assertEqual(result["modified_files_count"], 4)
        self.assertEqual(result["limit"], 10)

    def test_flags_unsafe_workspace(self):
        with self.patch_gate(11, ["f"] * 11)[0]:
            result = governance_handler.h_audit_changes({})
        self.assertFalse(result["is_safe"])
        self.assertEqual(len(result["files"]), 11)

    def test_exactly_at_the_limit_is_still_safe(self):
        """El límite son 10 archivos permitidos, no 9: el freno dispara al superarlo."""
        with self.patch_gate(10, ["f"] * 10, limit=10)[0]:
            result = governance_handler.h_audit_changes({})
        self.assertTrue(result["is_safe"])


class TestQualityGate(GovernanceTestCase):

    def test_blocks_before_running_tests_when_over_the_limit(self):
        """Un solo archivo de más ya frena: el gate no tolera holgura."""
        with self.patch_gate(11, ["f"] * 11, limit=10)[0], \
                mock.patch("lib.spec.tester.execute_tests_and_collect_errors") as run_tests:
            result = governance_handler.h_quality_gate({})

        self.assertFalse(result["passed"])
        self.assertEqual(result["stage"], "contencion")
        self.assertIn("11 archivos", result["message"])
        run_tests.assert_not_called()

    def test_blocking_starts_only_above_the_limit(self):
        """Con 10 archivos el gate corre los tests: el límite es inclusivo."""
        with self.patch_gate(10, ["f"] * 10, limit=10)[0], \
                mock.patch("lib.spec.tester.execute_tests_and_collect_errors", return_value=(True, [])):
            result = governance_handler.h_quality_gate({})

        self.assertTrue(result["passed"])
        self.assertEqual(result["stage"], "tests")

    def test_reports_passing_suite(self):
        with self.patch_gate(2)[0], \
                mock.patch("lib.spec.tester.execute_tests_and_collect_errors", return_value=(True, [])):
            result = governance_handler.h_quality_gate({})

        self.assertTrue(result["passed"])
        self.assertEqual(result["stage"], "tests")
        self.assertEqual(result["modified_files"], 2)
        self.assertEqual(result["errors"], [])

    def test_reports_failing_suite(self):
        with self.patch_gate(1)[0], \
                mock.patch("lib.spec.tester.execute_tests_and_collect_errors",
                           return_value=(False, ["boom"])):
            result = governance_handler.h_quality_gate({})

        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"], ["boom"])

    def test_suite_crash_is_reported_as_gate_error(self):
        with self.patch_gate(1)[0], \
                mock.patch("lib.spec.tester.execute_tests_and_collect_errors",
                           side_effect=ValueError("roto")):
            result = governance_handler.h_quality_gate({})

        self.assertFalse(result["passed"])
        self.assertEqual(result["stage"], "tests")
        self.assertEqual(result["error"], "ValueError: roto")


class TestCommit(GovernanceTestCase):

    def commit(self, args, count=1, git_results=None):
        results = git_results or {}
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            key = command[1] if len(command) > 1 else command[0]
            return results.get(key, mock.Mock(returncode=0, stdout="", stderr=""))

        patches = self.patch_gate(count, [" M a.py"])
        with patches[0], patches[1], \
                mock.patch.object(governance_handler.subprocess, "run", side_effect=fake_run):
            return governance_handler.h_commit(args), calls

    def test_rejects_missing_message(self):
        result, _ = self.commit({})
        self.assertFalse(result["committed"])
        self.assertIn("Falta 'message'", result["error"])

    def test_rejects_blank_message(self):
        result, _ = self.commit({"message": "   "})
        self.assertFalse(result["committed"])

    def test_rejects_co_authored_by_attribution(self):
        result, _ = self.commit({"message": "feat: algo\n\nCo-Authored-By: Bot <bot@x>"})
        self.assertFalse(result["committed"])
        self.assertIn("Co-Authored-By", result["error"])

    def test_rejects_ai_attribution_word(self):
        result, _ = self.commit({"message": "feat: add ai helper"})
        self.assertFalse(result["committed"])
        self.assertIn("atribución de IA", result["error"])

    def test_rejects_generated_with_and_robot_emoji(self):
        for message in ("feat: x generated with tool", "feat: x 🤖"):
            result, _ = self.commit({"message": message})
            self.assertFalse(result["committed"], message)

    def test_does_not_match_ai_inside_a_longer_word(self):
        result, calls = self.commit(
            {"message": "fix(core): repair the air pump"},
            git_results={"rev-parse": mock.Mock(returncode=0, stdout="abc1234\n", stderr="")},
        )
        self.assertTrue(result["committed"], result)
        self.assertIn(["git", "commit", "-m", "fix(core): repair the air pump"], calls)

    def test_rejects_non_conventional_message(self):
        result, _ = self.commit({"message": "arreglos varios"})
        self.assertFalse(result["committed"])
        self.assertIn("Conventional Commits", result["error"])

    def test_rejects_when_there_is_nothing_to_commit(self):
        result, _ = self.commit({"message": "feat: x"}, count=0)
        self.assertFalse(result["committed"])
        self.assertIn("No hay cambios", result["error"])

    def test_rejects_when_over_the_file_limit(self):
        result, _ = self.commit({"message": "feat: x"}, count=11)
        self.assertFalse(result["committed"])
        self.assertIn("Freno de contención", result["error"])
        self.assertEqual(len(result["files"]), 1)

    def test_commits_at_exactly_the_limit(self):
        result, _ = self.commit(
            {"message": "feat: x"},
            count=10,
            git_results={"rev-parse": mock.Mock(returncode=0, stdout="abc1234\n", stderr="")},
        )
        self.assertTrue(result["committed"], result)

    def test_commits_and_reports_short_hash(self):
        result, calls = self.commit(
            {"message": "feat(game): add orbital physics"},
            count=2,
            git_results={"rev-parse": mock.Mock(returncode=0, stdout="deadbee\n", stderr="")},
        )

        self.assertTrue(result["committed"])
        self.assertEqual(result["commit"], "deadbee")
        self.assertEqual(result["message"], "feat(game): add orbital physics")
        self.assertIn(["git", "add", "-A"], calls)
        self.assertIn(["git", "commit", "-m", "feat(game): add orbital physics"], calls)

    def test_git_failure_is_surfaced(self):
        result, _ = self.commit(
            {"message": "feat: x"},
            git_results={"commit": mock.Mock(returncode=1, stdout="", stderr="nada para commitear")},
        )
        self.assertFalse(result["committed"])
        self.assertEqual(result["error"], "nada para commitear")


# ---------------------------------------------------------------------------
# Mock
# ---------------------------------------------------------------------------
class TestLaunchCommand(unittest.TestCase):

    def test_prefers_prism_when_available(self):
        with mock.patch("lib.spec.mock_engine.find_prism_runner", return_value=["prism"]):
            command, engine = mock_handler._launch_command(Path("/w/openapi.yaml"), 4011)

        self.assertEqual(engine, "prism")
        self.assertEqual(command, ["prism", "mock", "/w/openapi.yaml", "-p", "4011"])

    def test_falls_back_to_native_python_server(self):
        with mock.patch("lib.spec.mock_engine.find_prism_runner", return_value=None):
            command, engine = mock_handler._launch_command(Path("/w/openapi.yaml"), 4012)

        self.assertEqual(engine, "python-native")
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], "-c")
        self.assertIn("run_native_python_mock", command[2])
        self.assertIn("/w/openapi.yaml", command[2])


class TestWaitUntilReady(unittest.TestCase):
    """El arranque del mock no puede bloquearse ni declarar éxito sin puerto."""

    def test_returns_true_as_soon_as_the_port_opens(self):
        process = mock.Mock()
        with mock.patch.object(mock_handler, "port_open", return_value=True):
            self.assertTrue(mock_handler._wait_until_ready(4010, process))

    def test_returns_false_when_the_process_dies(self):
        process = mock.Mock()
        process.poll.return_value = 1
        with mock.patch.object(mock_handler, "port_open", return_value=False), \
                mock.patch.object(mock_handler.time, "sleep") as sleep:
            self.assertFalse(mock_handler._wait_until_ready(4010, process))
        # Un proceso muerto corta la espera: no se agota el presupuesto durmiendo.
        sleep.assert_not_called()

    def test_gives_up_after_the_attempt_budget(self):
        process = mock.Mock()
        process.poll.return_value = None
        with mock.patch.object(mock_handler, "port_open", return_value=False), \
                mock.patch.object(mock_handler, "START_ATTEMPTS", 3), \
                mock.patch.object(mock_handler.time, "sleep") as sleep:
            self.assertFalse(mock_handler._wait_until_ready(4010, process))
        self.assertEqual(sleep.call_count, 3)


class TestMockStart(HandlerTestCase):

    def start(self, args=None, wait=True, spec="openapi.yaml", spec_found=True, returns=None):
        process = mock.Mock()
        process.pid = 4321
        process.poll.return_value = returns

        patches = [
            mock.patch.object(mock_handler, "port_open", return_value=False),
            mock.patch.object(mock_handler, "_wait_until_ready", return_value=wait),
            mock.patch.object(mock_handler, "_launch_command", return_value=(["prism"], "prism")),
            mock.patch.object(mock_handler.subprocess, "Popen", return_value=process),
            mock.patch.object(mock_handler, "write_mock_state"),
            mock.patch.object(mock_handler, "MOCK_LOG", self.root / "state" / "mock.log"),
            mock.patch.object(mock_handler, "STATE_DIR", self.root / "state"),
            mock.patch("lib.spec.mock_engine.find_openapi_spec",
                       return_value=(self.root / spec) if spec_found else None),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        result = mock_handler.h_mock_start(args or {})
        return result, process

    def test_reports_already_running_port_without_spawning(self):
        with mock.patch.object(mock_handler, "port_open", return_value=True), \
                mock.patch.object(mock_handler.subprocess, "Popen") as popen:
            result = mock_handler.h_mock_start({"port": 4010})

        self.assertEqual(result, {"started": False, "already_running": True, "port": 4010,
                                  "url": "http://localhost:4010"})
        popen.assert_not_called()

    def test_requires_a_contract(self):
        result, process = self.start(spec_found=False)
        self.assertFalse(result["started"])
        self.assertIn("chelo_init", result["error"])
        process.poll.assert_not_called()

    def test_starts_mock_and_registers_state(self):
        result, _ = self.start({"port": 4013})

        self.assertTrue(result["started"])
        self.assertEqual(result["engine"], "prism")
        self.assertEqual(result["pid"], 4321)
        self.assertEqual(result["port"], 4013)
        self.assertEqual(result["url"], "http://localhost:4013")
        self.assertEqual(result["spec"], str(self.root / "openapi.yaml"))
        self.assertEqual(result["log_file"], str(self.root / "state" / "mock.log"))

        stored = mock_handler.write_mock_state.call_args.args[0]
        self.assertEqual(stored["pid"], 4321)
        self.assertEqual(stored["pgid"], 4321)
        self.assertEqual(stored["engine"], "prism")
        self.assertEqual(stored["workspace"], str(self.root))

    def test_uses_default_port_when_not_given(self):
        with mock.patch("lib.spec.mock_engine.PRISM_PORT", 4999):
            result, _ = self.start()
        self.assertEqual(result["port"], 4999)

    def test_timeout_kills_process_group_and_returns_log_tail(self):
        log = self.root / "state" / "mock.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("\x1b[31mno arrancó\x1b[0m\n", encoding="utf-8")

        with mock.patch.object(mock_handler.os, "getpgid", return_value=4321), \
                mock.patch.object(mock_handler.os, "killpg") as killpg:
            result, _ = self.start(wait=False, returns=None)

        self.assertFalse(result["started"])
        self.assertEqual(result["engine"], "prism")
        self.assertIn("no arrancó", result["log_tail"])
        killpg.assert_called_once_with(4321, mock.ANY)
        mock_handler.write_mock_state.assert_not_called()

    def test_unreadable_log_does_not_break_the_timeout_report(self):
        """Si el log no se puede leer, el handler igual informa el fallo."""
        real_read = Path.read_text

        def broken(path_self, *args, **kwargs):
            if str(path_self).endswith("mock.log"):
                raise PermissionError("sin permisos")
            return real_read(path_self, *args, **kwargs)

        with mock.patch.object(Path, "read_text", broken):
            result, _ = self.start(wait=False, returns=1)

        self.assertFalse(result["started"])
        self.assertEqual(result["log_tail"], "")

    def test_timeout_with_dead_process_does_not_kill(self):
        with mock.patch.object(mock_handler.os, "killpg") as killpg:
            result, _ = self.start(wait=False, returns=1)

        self.assertFalse(result["started"])
        self.assertEqual(result["log_tail"], "")
        killpg.assert_not_called()


class TestMockStop(HandlerTestCase):

    def test_reports_when_nothing_is_registered(self):
        with mock.patch.object(mock_handler, "read_mock_state", return_value=None):
            result = mock_handler.h_mock_stop({})
        self.assertEqual(result, {"stopped": False, "message": "No hay mock registrado por chelo."})

    def test_signals_the_registered_pid_and_clears_state(self):
        state = {"pid": 111, "port": 4014}
        with mock.patch.object(mock_handler, "read_mock_state", return_value=state), \
                mock.patch.object(mock_handler, "_terminate", return_value=True), \
                mock.patch.object(mock_handler, "port_open", return_value=False), \
                mock.patch.object(mock_handler, "clear_mock_state") as clear:
            result = mock_handler.h_mock_stop({})

        self.assertTrue(result["stopped"])
        self.assertTrue(result["signalled"])
        self.assertEqual(result["pid"], 111)
        self.assertFalse(result["port_still_open"])
        clear.assert_called_once_with()

    def test_reports_port_that_never_closes(self):
        with mock.patch.object(mock_handler, "read_mock_state",
                               return_value={"pid": 111, "port": 4015}), \
                mock.patch.object(mock_handler, "_terminate", return_value=False), \
                mock.patch.object(mock_handler, "port_open", return_value=True), \
                mock.patch.object(mock_handler.time, "sleep"), \
                mock.patch.object(mock_handler, "clear_mock_state"):
            result = mock_handler.h_mock_stop({})

        self.assertTrue(result["stopped"])
        self.assertFalse(result["signalled"])
        self.assertTrue(result["port_still_open"])

    def test_terminate_signals_the_process_group(self):
        with mock.patch.object(mock_handler.os, "getpgid", return_value=777), \
                mock.patch.object(mock_handler.os, "killpg") as killpg:
            self.assertTrue(mock_handler._terminate(777))
        killpg.assert_called_once_with(777, mock.ANY)

    def test_terminate_falls_back_to_the_pid_when_the_group_is_gone(self):
        with mock.patch.object(mock_handler.os, "getpgid", side_effect=ProcessLookupError), \
                mock.patch.object(mock_handler.os, "kill") as kill:
            self.assertTrue(mock_handler._terminate(222))
        kill.assert_called_once_with(222, mock.ANY)

    def test_terminate_returns_false_when_the_process_is_gone(self):
        with mock.patch.object(mock_handler.os, "getpgid", side_effect=ProcessLookupError), \
                mock.patch.object(mock_handler.os, "kill", side_effect=ProcessLookupError):
            self.assertFalse(mock_handler._terminate(333))


class TestMockStatus(HandlerTestCase):

    def test_without_state_reports_unmanaged_defaults(self):
        with mock.patch.object(mock_handler, "read_mock_state", return_value=None), \
                mock.patch.object(mock_handler, "port_open", return_value=False), \
                mock.patch("lib.spec.mock_engine.PRISM_PORT", 4010):
            result = mock_handler.h_mock_status({})

        self.assertFalse(result["running"])
        self.assertFalse(result["managed"])
        self.assertEqual(result["port"], 4010)
        self.assertIsNone(result["pid"])
        self.assertFalse(result["pid_alive"])
        self.assertIsNone(result["engine"])

    def test_with_live_state_reports_pid_and_engine(self):
        state = {"pid": 555, "port": 4016, "engine": "python-native", "spec": "/w/openapi.yaml"}
        with mock.patch.object(mock_handler, "read_mock_state", return_value=state), \
                mock.patch.object(mock_handler, "port_open", return_value=True), \
                mock.patch.object(mock_handler.os, "kill", return_value=None):
            result = mock_handler.h_mock_status({})

        self.assertTrue(result["running"])
        self.assertTrue(result["managed"])
        self.assertTrue(result["pid_alive"])
        self.assertEqual(result["pid"], 555)
        self.assertEqual(result["port"], 4016)
        self.assertEqual(result["engine"], "python-native")
        self.assertEqual(result["spec"], "/w/openapi.yaml")

    def test_dead_pid_is_reported_as_not_alive(self):
        with mock.patch.object(mock_handler, "read_mock_state",
                               return_value={"pid": 556, "port": 4017}), \
                mock.patch.object(mock_handler, "port_open", return_value=False), \
                mock.patch.object(mock_handler.os, "kill", side_effect=ProcessLookupError):
            result = mock_handler.h_mock_status({})

        self.assertFalse(result["pid_alive"])
        self.assertFalse(result["running"])


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------
class TestMask(unittest.TestCase):

    def test_none_and_empty_are_not_masked(self):
        self.assertIsNone(workspace_handler._mask(None))
        self.assertIsNone(workspace_handler._mask(""))

    def test_short_values_reveal_nothing(self):
        self.assertEqual(workspace_handler._mask("12345678"), "…")
        self.assertEqual(workspace_handler._mask("abc"), "…")

    def test_long_values_reveal_only_the_edges(self):
        self.assertEqual(workspace_handler._mask("123456789"), "1234…6789")
        self.assertEqual(workspace_handler._mask("abcdefghijkl"), "abcd…ijkl")


class TestStack(HandlerTestCase):

    def test_reports_stack_spec_and_toolchain(self):
        spec = self.root / "openapi.yaml"
        with mock.patch("lib.core.stack_detector.detect_workspace_stack", return_value={"backend": "go"}), \
                mock.patch("lib.spec.mock_engine.find_openapi_spec", return_value=spec), \
                mock.patch("lib.spec.mock_engine.find_prism_runner", return_value="prism"), \
                mock.patch("lib.spec.tester.find_hurl_runner", return_value="hurl"), \
                mock.patch("lib.core.runner.find_opencode_runner", return_value="opencode"), \
                mock.patch("lib.core.runner.find_agent_runner", return_value="/bin/agent"):
            result = workspace_handler.h_stack({})

        self.assertEqual(result["workspace"], str(self.root))
        self.assertEqual(result["stack"], {"backend": "go"})
        self.assertEqual(result["spec"], str(spec))
        self.assertEqual(result["toolchain"], {
            "hurl": "hurl",
            "prism": "prism",
            "opencode": "opencode",
            "agent_runner": "/bin/agent",
        })

    def test_missing_spec_is_none(self):
        with mock.patch("lib.core.stack_detector.detect_workspace_stack", return_value={}), \
                mock.patch("lib.spec.mock_engine.find_openapi_spec", return_value=None), \
                mock.patch("lib.spec.mock_engine.find_prism_runner", return_value=None), \
                mock.patch("lib.spec.tester.find_hurl_runner", return_value=None), \
                mock.patch("lib.core.runner.find_opencode_runner", return_value=None), \
                mock.patch("lib.core.runner.find_agent_runner", return_value=None):
            result = workspace_handler.h_stack({})
        self.assertIsNone(result["spec"])


class TestDoctor(HandlerTestCase):

    def doctor(self, env=None):
        os.environ.update(env or {})
        with mock.patch("lib.spec.mock_engine.find_prism_runner", return_value=None), \
                mock.patch("lib.spec.tester.find_hurl_runner", return_value="hurl"), \
                mock.patch("lib.core.runner.find_opencode_runner", return_value="opencode"), \
                mock.patch("lib.core.runner.find_agent_runner", return_value=None), \
                mock.patch("shutil.which", side_effect=lambda name: "/usr/bin/gh" if name == "gh" else None):
            return workspace_handler.h_doctor({})

    def test_masks_keys_and_lists_configured_names(self):
        result = self.doctor({"GEMINI_API_KEY": "abcdefghijkl", "SLACK_BOT_TOKEN": "xoxb-secret-value"})

        self.assertEqual(result["api_keys"]["GEMINI_API_KEY"], "abcd…ijkl")
        self.assertEqual(result["api_keys"]["SLACK_BOT_TOKEN"], "xoxb…alue")
        self.assertIsNone(result["api_keys"]["OPENAI_API_KEY"])
        self.assertEqual(result["configured"], ["GEMINI_API_KEY", "SLACK_BOT_TOKEN"])

    def test_google_key_is_the_gemini_fallback(self):
        result = self.doctor({"GOOGLE_API_KEY": "google-key-1234"})
        self.assertEqual(result["api_keys"]["GEMINI_API_KEY"], "goog…1234")
        self.assertEqual(result["configured"], ["GEMINI_API_KEY"])

    def test_reports_toolchain_and_python(self):
        result = self.doctor()
        self.assertEqual(result["tools"]["hurl"], "hurl")
        self.assertEqual(result["tools"]["gh"], "/usr/bin/gh")
        self.assertIsNone(result["tools"]["prism"])
        self.assertEqual(result["tools"]["python"], sys.executable)
        self.assertEqual(result["configured"], [])


class TestWorkspaceInit(HandlerTestCase):

    def test_init_success_relays_ok_and_log(self):
        def fake_init():
            print("workspace inicializado")
            return {"ok": True}

        with mock.patch("lib.core.init_project.cmd_init", side_effect=fake_init):
            result = workspace_handler.h_init({})

        self.assertTrue(result["ok"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["log"], "workspace inicializado")

    def test_init_failure_becomes_an_error_payload(self):
        with mock.patch("lib.core.init_project.cmd_init", side_effect=RuntimeError("git roto")):
            result = workspace_handler.h_init({})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "RuntimeError: git roto")

    def test_board_init_forwards_force_as_boolean(self):
        with mock.patch("lib.core.board.board_init", return_value={"initialized": True}) as board_init:
            workspace_handler.h_board_init({"force": 1})
            board_init.assert_called_once_with(force=True)

            board_init.reset_mock()
            workspace_handler.h_board_init({"force": 0})
            board_init.assert_called_once_with(force=False)

            board_init.reset_mock()
            workspace_handler.h_board_init({})
            board_init.assert_called_once_with(force=False)

    def test_board_url_resolves_slug_and_url(self):
        with mock.patch("lib.core.board.repo_slug", return_value="jmrodev/daily-board"), \
                mock.patch("lib.core.board.board_url",
                           side_effect=lambda slug: f"https://{slug}.github.io/daily-board/"):
            result = workspace_handler.h_board_url({})

        self.assertEqual(result, {
            "slug": "jmrodev/daily-board",
            "url": "https://jmrodev/daily-board.github.io/daily-board/",
        })


# ---------------------------------------------------------------------------
# Canales ágiles
# ---------------------------------------------------------------------------
class TestSync(HandlerTestCase):

    def sync(self, args):
        with mock.patch("lib.channels.get_slack_messages", return_value={"messages": []}) as slack, \
                mock.patch("lib.channels.get_github_sprint_context", return_value={"issues": []}) as github:
            return channels_handler.h_sync(args), slack, github

    def test_queries_both_channels_with_defaults(self):
        result, slack, github = self.sync({})

        self.assertEqual(result, {"slack": {"messages": []}, "github": {"issues": []}})
        slack.assert_called_once_with(channel_id=None, limit=5)
        github.assert_called_once_with()

    def test_forwards_channel_and_limit(self):
        _, slack, _ = self.sync({"channel_id": "C123", "slack_limit": "3"})
        slack.assert_called_once_with(channel_id="C123", limit=3)

    def test_limit_of_zero_falls_back_to_default(self):
        _, slack, _ = self.sync({"slack_limit": 0})
        slack.assert_called_once_with(channel_id=None, limit=5)

    def test_can_skip_each_channel(self):
        result, slack, github = self.sync({"include_slack": False, "include_github": False})

        self.assertEqual(result, {"slack": None, "github": None})
        slack.assert_not_called()
        github.assert_not_called()

    def test_slack_only(self):
        result, _, github = self.sync({"include_github": False})
        self.assertIsNone(result["github"])
        github.assert_not_called()


class TestSlackPost(HandlerTestCase):

    def test_rejects_blank_text_without_calling_slack(self):
        with mock.patch("lib.channels.post_slack_message") as post:
            result = channels_handler.h_slack_post({"text": "   "})

        self.assertFalse(result["ok"])
        self.assertIn("Falta el texto", result["error"])
        post.assert_not_called()

    def test_posts_trimmed_text_and_relays_the_result(self):
        with mock.patch("lib.channels.post_slack_message",
                        return_value={"ok": True, "channel": "C1"}) as post:
            result = channels_handler.h_slack_post({"text": "  hola  ", "channel_id": "C1"})

        post.assert_called_once_with("hola", channel_id="C1")
        self.assertEqual(result, {"ok": True, "channel": "C1"})


# ---------------------------------------------------------------------------
# Agentes
# ---------------------------------------------------------------------------
class TestAgentTurn(HandlerTestCase):

    def turn(self, args, prompt="sos un agente", response=None, available=None):
        response = response if response is not None else {
            "ok": True, "text": "respuesta", "model_used": "gemini",
        }
        with mock.patch("lib.core.runner.get_agent_prompt", return_value=prompt), \
                mock.patch.object(agents_handler, "available_roles",
                                  return_value=available or ["story-agent"]), \
                mock.patch("lib.orchestration.run_agent_turn", return_value=response) as run:
            return agents_handler.h_agent_turn(args), run

    def test_requires_role_and_instruction(self):
        for args in ({}, {"role": "story-agent"}, {"instruction": "x"}, {"role": " ", "instruction": " "}):
            result, run = self.turn(args)
            self.assertFalse(result["ok"], args)
            self.assertIn("'role' e 'instruction'", result["error"])
            run.assert_not_called()

    def test_rejects_unknown_role_and_lists_available_ones(self):
        result, run = self.turn({"role": "no-existe", "instruction": "x"}, prompt=None,
                                available=["qa-tester"])

        self.assertFalse(result["ok"])
        self.assertIn("Rol desconocido", result["error"])
        self.assertEqual(result["available_roles"], ["qa-tester"])
        run.assert_not_called()

    def test_relays_model_failure(self):
        result, _ = self.turn(
            {"role": "story-agent", "instruction": "x"},
            response={"ok": False, "error": "quota agotada", "model_used": "gemini"},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "quota agotada")
        self.assertEqual(result["model_used"], "gemini")

    def test_strips_markdown_fences_from_the_artifact(self):
        result, _ = self.turn(
            {"role": "story-agent", "instruction": "x"},
            response={"ok": True, "text": "```markdown\n# Historia\n```", "model_used": "gemini"},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "# Historia")
        self.assertIsNone(result["written_to"])
        self.assertFalse(result["used_tools"])

    def test_forwards_tool_options(self):
        _, run = self.turn({"role": "qa-tester", "instruction": "x", "use_tools": True,
                            "max_steps": 9, "context": "ctx"})
        run.assert_called_once_with("qa-tester", "x", context="ctx", trace=False,
                                    use_tools=True, max_steps=9)

    def test_out_path_outside_the_workspace_is_rejected(self):
        for out_path in ("../escape.md", "/tmp/absolute.md", "~/home.md"):
            result, _ = self.turn({"role": "story-agent", "instruction": "x", "out_path": out_path})
            self.assertFalse(result["ok"], out_path)
            self.assertIn("fuera del workspace", result["error"])

    def test_out_path_writes_the_artifact_inside_the_workspace(self):
        result, _ = self.turn({"role": "story-agent", "instruction": "x",
                               "out_path": "docs/historia.md"})

        target = self.root / "docs" / "historia.md"
        self.assertTrue(result["ok"])
        self.assertEqual(result["written_to"], str(target))
        self.assertEqual(target.read_text(encoding="utf-8"), "respuesta")


class TestPipeline(HandlerTestCase):

    def test_requires_a_requirement(self):
        result = agents_handler.h_pipeline({})
        self.assertFalse(result["ok"])
        self.assertIn("Falta 'requirement'", result["error"])

    def test_success_detects_the_completion_line_in_the_log(self):
        def fake_pipeline(project, requirement, trace):
            print(f"Pipeline Spec-First completado para {project}: {requirement}")

        with mock.patch("lib.orchestration.run_pipeline", side_effect=fake_pipeline):
            result = agents_handler.h_pipeline({"requirement": "crear juego"})

        self.assertTrue(result["ok"])
        self.assertIsNone(result["error"])
        self.assertTrue(result["completed"])
        self.assertIn("crear juego", result["log"])

    def test_defaults_project_to_the_workspace_directory_name(self):
        seen = {}

        def fake_pipeline(project, requirement, trace):
            seen.update(project=project, requirement=requirement, trace=trace)

        with mock.patch("lib.orchestration.run_pipeline", side_effect=fake_pipeline):
            agents_handler.h_pipeline({"requirement": "x", "trace": True})

        self.assertEqual(seen["project"], self.root.name)
        self.assertEqual(seen["requirement"], "x")
        self.assertTrue(seen["trace"])

    def test_incomplete_pipeline_is_not_reported_as_completed(self):
        def fake_pipeline(project, requirement, trace):
            print("falló en el paso 2")

        with mock.patch("lib.orchestration.run_pipeline", side_effect=fake_pipeline):
            result = agents_handler.h_pipeline({"requirement": "x"})

        self.assertTrue(result["ok"])
        self.assertFalse(result["completed"])

    def test_a_log_that_merely_mentions_completion_is_not_success(self):
        """El marcador es la línea exacta: 'no completado' no puede pasar por éxito."""
        def fake_pipeline(project, requirement, trace):
            print("Pipeline Spec-First no completado: abortado")

        with mock.patch("lib.orchestration.run_pipeline", side_effect=fake_pipeline):
            result = agents_handler.h_pipeline({"requirement": "x"})

        self.assertFalse(result["completed"])

    def test_crash_becomes_an_error_payload(self):
        with mock.patch("lib.orchestration.run_pipeline", side_effect=RuntimeError("sin API key")):
            result = agents_handler.h_pipeline({"requirement": "x"})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "RuntimeError: sin API key")
        self.assertFalse(result["completed"])


if __name__ == "__main__":
    unittest.main()
