#!/usr/bin/env python3
"""
Tests del servidor MCP de Chelo-Harness (protocolo JSON-RPC por stdio).

No tocan red ni API keys: solo verifican el contrato del servidor.
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent / "lib" / "chelo_mcp.py"


def speak(requests, timeout=30):
    payload = "\n".join(json.dumps(item) for item in requests) + "\n"
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()], proc.stderr


def call_tool(name, arguments=None, request_id=99):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }


class TestCheloMcp(unittest.TestCase):

    def test_initialize_reports_server(self):
        responses, _ = speak([
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"}}},
        ])
        self.assertEqual(len(responses), 1)
        result = responses[0]["result"]
        self.assertEqual(result["serverInfo"]["name"], "chelo-harness")
        self.assertIn("tools", result["capabilities"])

    def test_tools_list_exposes_full_surface(self):
        responses, _ = speak([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
        tools = responses[0]["result"]["tools"]
        names = [tool["name"] for tool in tools]

        expected = {
            "chelo_status", "chelo_audit_changes", "chelo_stack", "chelo_doctor",
            "chelo_spec_read", "chelo_mock_start", "chelo_mock_stop", "chelo_mock_status",
            "chelo_contract_test", "chelo_quality_gate", "chelo_init", "chelo_sync",
            "chelo_slack_post", "chelo_agent_turn", "chelo_pipeline", "chelo_commit",
            "chelo_board_init", "chelo_board_url",
        }
        self.assertEqual(set(names), expected)
        self.assertEqual(len(names), len(set(names)), "Los nombres de tools no deben repetirse")

    def test_every_tool_has_valid_schema(self):
        responses, _ = speak([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
        for tool in responses[0]["result"]["tools"]:
            self.assertTrue(tool.get("description"), f"{tool['name']} sin descripción")
            schema = tool.get("inputSchema", {})
            self.assertEqual(schema.get("type"), "object", f"{tool['name']} con schema inválido")
            self.assertIn("workspace", schema.get("properties", {}), f"{tool['name']} sin workspace")

    def test_notifications_never_get_a_response(self):
        responses, _ = speak([
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 7, "method": "ping"},
        ])
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["id"], 7)

    def test_unknown_method_returns_minus_32601(self):
        responses, _ = speak([{"jsonrpc": "2.0", "id": 3, "method": "no/existe"}])
        self.assertEqual(responses[0]["error"]["code"], -32601)

    def test_unknown_tool_is_a_tool_error(self):
        responses, _ = speak([call_tool("chelo_no_existe")])
        self.assertTrue(responses[0]["result"]["isError"])

    def test_agent_turn_rejects_unknown_role(self):
        responses, _ = speak([call_tool("chelo_agent_turn", {"role": "no-existe", "instruction": "x"})])
        payload = json.loads(responses[0]["result"]["content"][0]["text"])
        self.assertFalse(payload["ok"])
        self.assertIn("story-agent", payload["available_roles"])

    def test_stdout_is_pure_json(self):
        """Ninguna librería puede contaminar el canal del protocolo."""
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}) + "\n"
        proc = subprocess.run(
            [sys.executable, str(SERVER)], input=payload, capture_output=True, text=True, timeout=30
        )
        for line in proc.stdout.splitlines():
            if line.strip():
                json.loads(line)


if __name__ == "__main__":
    unittest.main()
