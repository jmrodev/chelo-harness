#!/usr/bin/env python3
"""
Tests del sandbox de tools de agentes y del bucle de function calling.

No llaman a Gemini ni a la red: el cliente se monkeypatchea.
"""

import os
import tempfile
import unittest
from pathlib import Path

from lib.ai import gemini_client
from lib.ai.tools import (
    AVAILABLE_AGENT_TOOLS,
    AVAILABLE_TOOLS,
    AGENT_TOOL_DECLARATIONS,
    tool_list_dir,
    tool_read_file,
    tool_write_doc,
)


class SandboxCase(unittest.TestCase):
    """Cada test corre en un workspace temporal vacío."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._previous = Path.cwd()
        os.chdir(self._tmp.name)
        self.root = Path.cwd()

    def tearDown(self):
        os.chdir(self._previous)
        self._tmp.cleanup()


class TestWriteDocSandbox(SandboxCase):

    def test_writes_inside_docs(self):
        result = tool_write_doc("stories/US-001.md", "# Historia")
        self.assertTrue(result["ok"], result)
        self.assertTrue((self.root / "docs" / "stories" / "US-001.md").is_file())

    def test_rejects_parent_escape(self):
        result = tool_write_doc("../fuera.md", "x")
        self.assertFalse(result["ok"])
        self.assertIn("docs/", result["error"])
        self.assertFalse((self.root.parent / "fuera.md").exists())

    def test_rejects_deep_escape(self):
        result = tool_write_doc("../../../../tmp/fuera.md", "x")
        self.assertFalse(result["ok"])
        self.assertFalse(Path("/tmp/fuera.md").exists())

    def test_rejects_absolute_path(self):
        target = self.root / "absoluto.md"
        result = tool_write_doc(str(target), "x")
        self.assertFalse(result["ok"])
        self.assertFalse(target.exists())

    def test_rejects_empty_path(self):
        self.assertFalse(tool_write_doc("", "x")["ok"])

    def test_accepts_docs_prefix_redundantly(self):
        """El modelo a veces manda 'docs/x.md' aunque ya esté dentro de docs/."""
        result = tool_write_doc("docs/nota.md", "contenido")
        self.assertTrue(result["ok"], result)
        self.assertTrue((self.root / "docs" / "nota.md").is_file())
        self.assertFalse((self.root / "docs" / "docs").exists())


class TestReadSandbox(SandboxCase):

    def test_reads_workspace_file(self):
        (self.root / "openapi.yaml").write_text("openapi: 3.0.0", encoding="utf-8")
        result = tool_read_file("openapi.yaml")
        self.assertTrue(result["ok"])
        self.assertIn("openapi", result["content"])

    def test_rejects_escape(self):
        secret = self.root.parent / "secreto.txt"
        secret.write_text("no deberías leer esto", encoding="utf-8")
        try:
            result = tool_read_file("../secreto.txt")
            self.assertFalse(result["ok"])
            self.assertNotIn("no deberías", str(result.get("content", "")))
        finally:
            secret.unlink()

    def test_listing_does_not_crash_on_root(self):
        (self.root / "docs").mkdir()
        result = tool_list_dir(".")
        self.assertTrue(result["ok"], result)


class TestAgentToolSet(unittest.TestCase):

    def test_run_command_is_not_available_to_agents(self):
        self.assertNotIn("run_command", AVAILABLE_AGENT_TOOLS)
        self.assertIn("run_command", AVAILABLE_TOOLS, "la tool cruda sigue existiendo para uso explícito")

    def test_agent_set_is_minimal(self):
        self.assertEqual(set(AVAILABLE_AGENT_TOOLS), {"read_file", "list_dir", "write_doc"})

    def test_declarations_match_the_agent_set(self):
        declared = {
            fn["name"]
            for block in AGENT_TOOL_DECLARATIONS
            for fn in block["functionDeclarations"]
        }
        self.assertEqual(declared, set(AVAILABLE_AGENT_TOOLS))


class TestToolsLoop(unittest.TestCase):

    def _patch(self, responses):
        """Reemplaza generate_content y devuelve la lista de contents enviados."""
        seen = []
        queue = list(responses)

        def fake(contents, system_instruction=None, enable_tools=False, **kwargs):
            seen.append(contents)
            return queue.pop(0)

        original = gemini_client.generate_content
        gemini_client.generate_content = fake
        self.addCleanup(setattr, gemini_client, "generate_content", original)
        return seen

    def test_returns_final_text_when_model_stops(self):
        self._patch([{"ok": True, "is_tool_call": False, "text": "listo"}])
        result = gemini_client.run_with_tools_loop("hacé algo")
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "listo")

    def test_executes_tool_and_feeds_response_back(self):
        seen = self._patch([
            {"ok": True, "is_tool_call": True, "tool_name": "read_file",
             "tool_args": {"path": "openapi.yaml"},
             "raw_parts": [{"functionCall": {"name": "read_file", "args": {"path": "openapi.yaml"}}}]},
            {"ok": True, "is_tool_call": False, "text": "leído"},
        ])
        Path("openapi.yaml").write_text("openapi: 3.0.0", encoding="utf-8")
        try:
            result = gemini_client.run_with_tools_loop("leé el contrato")
            self.assertEqual(result["text"], "leído")
            last = seen[-1][-1]
            self.assertEqual(last["role"], "function")
            self.assertTrue(last["parts"][0]["functionResponse"]["response"]["ok"])
        finally:
            Path("openapi.yaml").unlink()

    def test_rejects_tool_outside_the_provided_subset(self):
        seen = self._patch([
            {"ok": True, "is_tool_call": True, "tool_name": "run_command",
             "tool_args": {"cmd": "rm -rf /"},
             "raw_parts": [{"functionCall": {"name": "run_command", "args": {"cmd": "rm -rf /"}}}]},
            {"ok": True, "is_tool_call": False, "text": "ok"},
        ])
        result = gemini_client.run_with_tools_loop("x", tools={"read_file": tool_read_file})
        self.assertEqual(result["text"], "ok")
        payload = seen[-1][-1]["parts"][0]["functionResponse"]["response"]
        self.assertFalse(payload["ok"])
        self.assertIn("no está habilitada", payload["error"])

    def test_reports_step_limit(self):
        self._patch([
            {"ok": True, "is_tool_call": True, "tool_name": "read_file",
             "tool_args": {"path": "a"}, "raw_parts": [{"functionCall": {"name": "read_file", "args": {"path": "a"}}}]},
            {"ok": True, "is_tool_call": True, "tool_name": "read_file",
             "tool_args": {"path": "a"}, "raw_parts": [{"functionCall": {"name": "read_file", "args": {"path": "a"}}}]},
        ])
        result = gemini_client.run_with_tools_loop("x", max_steps=2)
        self.assertFalse(result["ok"])
        self.assertIn("Límite", result["error"])

    def test_notifies_each_step(self):
        self._patch([
            {"ok": True, "is_tool_call": True, "tool_name": "list_dir",
             "tool_args": {}, "raw_parts": [{"functionCall": {"name": "list_dir", "args": {}}}]},
            {"ok": True, "is_tool_call": False, "text": "ok"},
        ])
        steps = []
        gemini_client.run_with_tools_loop("x", on_step=lambda **kw: steps.append(kw))
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["tool_name"], "list_dir")


class TestRunAgentTurnWiring(unittest.TestCase):
    """run_agent_turn debe entrar al bucle de tools solo cuando se lo piden."""

    def setUp(self):
        from lib.core import orchestrator

        self.orchestrator = orchestrator
        self._prompt = orchestrator.get_agent_prompt
        orchestrator.get_agent_prompt = lambda role: "sos un agente confinado"
        self.addCleanup(setattr, orchestrator, "get_agent_prompt", self._prompt)

    def _patch_loop(self):
        seen = []
        original = gemini_client.run_with_tools_loop

        def fake(prompt, system_instruction=None, max_steps=5, tools=None,
                 declarations=None, on_step=None):
            seen.append({"tools": tools, "max_steps": max_steps})
            return {"ok": True, "text": "artefacto", "model_used": "fake"}

        gemini_client.run_with_tools_loop = fake
        self.addCleanup(setattr, gemini_client, "run_with_tools_loop", original)
        return seen

    def _patch_direct(self):
        seen = []
        original = gemini_client.generate_content

        def fake(prompt, system_instruction=None, **kwargs):
            seen.append(kwargs)
            return {"ok": True, "text": "texto", "model_used": "fake"}

        gemini_client.generate_content = fake
        self.addCleanup(setattr, gemini_client, "generate_content", original)
        return seen

    def test_use_tools_enters_the_loop_with_the_safe_subset(self):
        seen = self._patch_loop()
        result = self.orchestrator.run_agent_turn("story-agent", "hacé algo", use_tools=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "artefacto")
        self.assertEqual(len(seen), 1)
        self.assertEqual(set(seen[0]["tools"]), {"read_file", "list_dir", "write_doc"})
        self.assertNotIn("run_command", seen[0]["tools"])

    def test_default_stays_single_shot(self):
        seen = self._patch_direct()
        result = self.orchestrator.run_agent_turn("story-agent", "hacé algo")

        self.assertEqual(result["text"], "texto")
        self.assertNotIn("tool_declarations", seen[0])


class TestHistoryTrim(unittest.TestCase):
    def test_never_orphans_a_function_response(self):
        contents = [{"role": "user", "parts": []}]
        for _ in range(8):
            contents.append({"role": "model", "parts": []})
            contents.append({"role": "function", "parts": []})

        trimmed = gemini_client._trim_contents(contents, limit=12, keep=10)
        self.assertLessEqual(len(trimmed), 12)
        self.assertEqual(trimmed[0]["role"], "user")
        self.assertNotEqual(trimmed[1]["role"], "function")

    def test_short_history_is_untouched(self):
        contents = [{"role": "user", "parts": []}, {"role": "model", "parts": []}]
        self.assertEqual(gemini_client._trim_contents(contents), contents)


if __name__ == "__main__":
    unittest.main()
