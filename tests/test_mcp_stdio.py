#!/usr/bin/env python3
"""
Regresión de invariantes del servidor MCP por stdio.

Dos defectos reales que esta suite fija:

1. Un subproceso dentro de un handler hereda el fd 1 del servidor. Como stdout
   es el canal JSON-RPC, `redirect_stdout` no alcanza: cualquier línea suelta
   rompe el protocolo del lado del cliente.
2. Un `workspace` explícito que no existe no puede caer al cwd del servidor y
   devolver éxito operando sobre otro repositorio.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SERVER = REPO / "lib" / "chelo_mcp.py"


def speak(requests, cwd, timeout=120):
    env = dict(os.environ, PYTHONPATH=str(REPO))
    return subprocess.run(
        [sys.executable, str(SERVER)],
        input="\n".join(json.dumps(item) for item in requests) + "\n",
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=timeout,
    )


def call_tool(name, arguments, request_id=1):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def first_result(proc):
    return json.loads([line for line in proc.stdout.splitlines() if line.strip()][0])["result"]


class TestStdoutPurity(unittest.TestCase):

    def test_first_chelo_init_keeps_stdout_json_only(self):
        """`git init` en un repo inexistente es el caso que filtraba texto a stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "fresh"
            workspace.mkdir()

            proc = speak([call_tool("chelo_init", {"workspace": str(workspace)})], cwd=tmp)

            self.assertEqual(proc.returncode, 0, proc.stderr)
            lines = [line for line in proc.stdout.splitlines() if line.strip()]
            self.assertEqual(len(lines), 1, f"stdout contaminado: {lines!r}")
            json.loads(lines[0])

    def test_repeated_init_is_still_pure(self):
        """El segundo init sobre un repo ya inicializado no debe regresar el defecto."""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "twice"
            workspace.mkdir()

            for _ in range(2):
                proc = speak([call_tool("chelo_init", {"workspace": str(workspace)})], cwd=tmp)
                lines = [line for line in proc.stdout.splitlines() if line.strip()]
                self.assertEqual(len(lines), 1, f"stdout contaminado: {lines!r}")


class TestWorkspaceValidation(unittest.TestCase):

    def test_invalid_workspace_is_an_error_not_a_silent_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "missing")

            proc = speak([call_tool("chelo_status", {"workspace": missing})], cwd=tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            result = first_result(proc)
            self.assertTrue(result["isError"], result)
            payload = json.loads(result["content"][0]["text"])
            self.assertIn("no existe", payload["error"])
            self.assertNotIn(tmp, payload.get("workspace", ""))


class TestSpecReadConfinement(unittest.TestCase):

    def test_spec_read_cannot_escape_the_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            (Path(tmp) / "secreto.yaml").write_text("secreto: true", encoding="utf-8")

            proc = speak(
                [call_tool("chelo_spec_read", {"workspace": str(workspace), "path": "../secreto.yaml"})],
                cwd=tmp,
            )
            payload = json.loads(first_result(proc)["content"][0]["text"])
            self.assertFalse(payload["found"], payload)
            self.assertIsNone(payload.get("content"))


if __name__ == "__main__":
    unittest.main()
