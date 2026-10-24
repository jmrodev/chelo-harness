#!/usr/bin/env python3
"""
Test suite de unidad y regresión para los componentes modulares de Chelo-Harness.
"""

import unittest
from pathlib import Path
from lib.core.gate import MAX_ALLOWED_CHANGES, audit_changes_rule
from lib.spec.mock_engine import find_openapi_spec, PRISM_PORT
from lib.ai.tools import AVAILABLE_TOOLS, tool_list_dir, tool_read_file
from lib.core.runner import get_agent_prompt

class TestCheloHarnessCore(unittest.TestCase):

    def test_gate_constants(self):
        self.assertEqual(MAX_ALLOWED_CHANGES, 10, "El disyuntor debe tener un límite estricto de 10 archivos")

    def test_ai_tools_available(self):
        expected_tools = ["read_file", "write_file", "list_dir", "run_command"]
        for tool in expected_tools:
            self.assertIn(tool, AVAILABLE_TOOLS, f"La herramienta {tool} debe estar disponible en AVAILABLE_TOOLS")

    def test_tool_list_dir(self):
        res = tool_list_dir(".")
        self.assertTrue(res.get("ok"), "tool_list_dir debe retornar ok=True en directorio actual")
        self.assertIn("bin", res.get("entries", []))
        self.assertIn("lib", res.get("entries", []))

    def test_tool_read_file(self):
        res = tool_read_file("LICENSE")
        self.assertTrue(res.get("ok"))
        self.assertIn("MIT License", res.get("content", ""))

    def test_runner_agent_prompts(self):
        agents = ["lead-architect", "story-agent", "spec-architect", "qa-tester"]
        for agent in agents:
            prompt = get_agent_prompt(agent)
            self.assertTrue(len(prompt) > 0, f"El prompt de {agent} no debe ser vacío")

    def test_prism_port_default(self):
        self.assertEqual(PRISM_PORT, 4010, "El puerto predeterminado de Prism debe ser 4010")

if __name__ == "__main__":
    unittest.main()
