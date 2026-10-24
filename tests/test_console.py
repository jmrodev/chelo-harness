#!/usr/bin/env python3
"""
Tests de la consola (`lib/ui/console.py`).

Fijan el comportamiento visible para el usuario: qué se imprime, con qué colores
y en qué orden. No dependen de que `rich` o `bat` estén instalados: las dos ramas
del render se ejercitan inyectando los módulos o simulando su ausencia.
"""

import io
import sys
import types
import unittest
from unittest import mock

from lib.ui import console


class TestRenderMarkdownSmooth(unittest.TestCase):

    def test_uses_rich_when_it_is_available(self):
        rich_console = types.ModuleType("rich.console")
        printed = mock.Mock()
        rich_console.Console = mock.Mock(return_value=mock.Mock(print=printed))

        rich_markdown = types.ModuleType("rich.markdown")
        rich_markdown.Markdown = mock.Mock(side_effect=lambda text: ("markdown", text))

        rich_panel = types.ModuleType("rich.panel")
        rich_panel.Panel = mock.Mock(side_effect=lambda body, **kwargs: ("panel", body, kwargs))

        modules = {
            "rich.console": rich_console,
            "rich.markdown": rich_markdown,
            "rich.panel": rich_panel,
        }
        with mock.patch.dict(sys.modules, modules):
            console.render_markdown_smooth("# Título\n\ncuerpo")

        rich_markdown.Markdown.assert_called_once_with("# Título\n\ncuerpo")
        printed.assert_called_once()
        kind, body, kwargs = printed.call_args.args[0]
        self.assertEqual(kind, "panel")
        self.assertEqual(body, ("markdown", "# Título\n\ncuerpo"))
        self.assertEqual(kwargs["border_style"], "cyan")
        self.assertIn("Lead-Architect", kwargs["title"])

    def test_falls_back_to_bat_when_rich_is_missing(self):
        process = mock.Mock()
        with mock.patch.dict(sys.modules, {"rich.console": None}), \
                mock.patch.object(console.shutil, "which", return_value="/usr/bin/bat"), \
                mock.patch.object(console.subprocess, "Popen", return_value=process) as popen, \
                mock.patch("builtins.print") as printed:
            console.render_markdown_smooth("# texto")

        popen.assert_called_once_with(
            ["bat", "--language=markdown", "--style=plain", "--paging=never"],
            stdin=console.subprocess.PIPE,
            text=True,
        )
        process.communicate.assert_called_once_with(input="# texto")
        printed.assert_not_called()

    def test_prints_plain_text_when_neither_tool_is_available(self):
        with mock.patch.dict(sys.modules, {"rich.console": None}), \
                mock.patch.object(console.shutil, "which", return_value=None), \
                mock.patch("builtins.print") as printed:
            console.render_markdown_smooth("# texto")

        printed.assert_called_once_with("# texto")


class TestStreamTypewriter(unittest.TestCase):

    def stream(self, text, **kwargs):
        buffer = io.StringIO()
        with mock.patch.object(console.sys, "stdout", buffer), \
                mock.patch.object(console.time, "sleep") as sleep:
            console.stream_typewriter(text, **kwargs)
        return buffer.getvalue(), sleep.call_args_list

    def test_writes_the_text_with_a_newline_per_line(self):
        output, _ = self.stream("Hola.\nChau", char_delay=0, line_delay=0)
        self.assertEqual(output, "Hola.\nChau\n")

    def test_empty_text_still_emits_one_line_break(self):
        output, _ = self.stream("", char_delay=0, line_delay=0)
        self.assertEqual(output, "\n")

    def test_punctuation_pauses_three_times_longer(self):
        for punctuation in (".", ",", "!", "?"):
            with self.subTest(punctuation=punctuation):
                _, sleeps = self.stream("A" + punctuation, char_delay=0.01, line_delay=0.5)
                delays = [call.args[0] for call in sleeps]
                self.assertEqual(delays.count(0.01 * 3), 1)
                self.assertEqual(delays.count(0.01), 1)
                self.assertEqual(delays[-1], 0.5)

    def test_other_characters_pay_only_the_base_delay(self):
        _, sleeps = self.stream("abc", char_delay=0.01, line_delay=0.5)
        delays = [call.args[0] for call in sleeps]
        self.assertEqual(delays.count(0.01), 3)
        self.assertNotIn(0.01 * 3, delays)

    def test_every_line_pays_the_line_delay(self):
        _, sleeps = self.stream("uno\ndos\ntres", char_delay=0, line_delay=0.2)
        line_delays = [call.args[0] for call in sleeps if call.args[0] == 0.2]
        self.assertEqual(len(line_delays), 3)


class TestSmoothPrint(unittest.TestCase):

    def test_prints_and_waits(self):
        with mock.patch("builtins.print") as printed, \
                mock.patch.object(console.time, "sleep") as sleep:
            console.smooth_print("hola", delay=0.3)

        printed.assert_called_once_with("hola")
        sleep.assert_called_once_with(0.3)

    def test_defaults_to_a_blank_line(self):
        with mock.patch("builtins.print") as printed, \
                mock.patch.object(console.time, "sleep"):
            console.smooth_print()
        printed.assert_called_once_with("")


class TestBanner(unittest.TestCase):

    def test_renders_the_version_inside_the_colour_codes(self):
        buffer = io.StringIO()
        with mock.patch.object(console.sys, "stdout", buffer):
            console.banner()

        output = buffer.getvalue()
        self.assertIn("CHELO-HARNESS v1.0.0", output)
        self.assertIn("Gobernanza Spec-First", output)
        self.assertTrue(output.startswith(console.CYAN))
        self.assertIn(console.NC, output)


class TestPromptText(unittest.TestCase):

    def prompt(self, answer, **kwargs):
        with mock.patch("builtins.input", return_value=answer) as reader:
            value = console.prompt_text(**kwargs)
        return value, reader.call_args.args[0]

    def test_returns_the_typed_value_stripped(self):
        value, _ = self.prompt("  produccion  ", label="Entorno")
        self.assertEqual(value, "produccion")

    def test_empty_answer_falls_back_to_the_default(self):
        value, _ = self.prompt("   ", label="Entorno", default="dev")
        self.assertEqual(value, "dev")

    def test_shows_the_default_in_the_prompt(self):
        _, prompt = self.prompt("", label="Entorno", default="dev")
        self.assertIn("[dev]", prompt)
        self.assertIn("Entorno", prompt)

    def test_hides_the_brackets_without_a_default(self):
        _, prompt = self.prompt("x", label="Entorno")
        self.assertTrue(prompt.endswith(f":{console.NC} "))
        self.assertNotIn("[]", prompt)
        self.assertIn(console.CYAN, prompt)


if __name__ == "__main__":
    unittest.main()
