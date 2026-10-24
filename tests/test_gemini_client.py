#!/usr/bin/env python3
"""
Tests del cliente de Gemini (`lib/ai/gemini_client.py`).

Todo el transporte HTTP está simulado: ninguna llamada sale a la red y no hace
falta una API key real. Lo que se fija acá es el contrato observable del
cliente: qué payload arma, cuándo rota de modelo, cómo interpreta una respuesta
con o sin functionCall, y cómo trata los errores del API.
"""

import io
import json
import unittest
import urllib.error
from unittest import mock

from lib.ai import gemini_client
from lib.ai.tools import TOOL_DECLARATIONS


class FakeResponse:
    """Respuesta mínima con la forma que usa `urlopen` como context manager."""

    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def http_error(code, body=b"detalle"):
    return urllib.error.HTTPError("https://api", code, "error", {}, io.BytesIO(body))


def text_payload(text="hola"):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def tool_payload(name="read_file", args=None, prefix_text=None):
    parts = []
    if prefix_text:
        parts.append({"text": prefix_text})
    parts.append({"functionCall": {"name": name, "args": args or {}}})
    return {"candidates": [{"content": {"parts": parts}}]}


class GeminiCase(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False)
        self.env.start()
        self.addCleanup(self.env.stop)
        import os

        os.environ.pop("GOOGLE_API_KEY", None)

    def call(self, side_effect=None, return_value=None, **kwargs):
        """Ejecuta generate_content con urlopen simulado y devuelve (resultado, requests)."""
        requests = []

        def fake_urlopen(request, timeout=None):
            requests.append(request)
            outcome = side_effect.pop(0) if side_effect else return_value
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch.object(gemini_client.urllib.request, "urlopen", fake_urlopen):
            result = gemini_client.generate_content(**kwargs)
        return result, requests


class TestGenerateContentInputs(GeminiCase):

    def test_requires_an_api_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = gemini_client.generate_content("hola")
        self.assertFalse(result["ok"])
        self.assertIn("GEMINI_API_KEY", result["error"])
        self.assertIn("setup", result["error"])

    def test_accepts_google_api_key_as_fallback(self):
        with mock.patch.dict("os.environ", {"GOOGLE_API_KEY": "google-key"}, clear=True):
            result, requests = self.call(return_value=FakeResponse(text_payload()),
                                          prompt_or_contents="x")
        self.assertTrue(result["ok"])
        self.assertIn("key=google-key", requests[0].full_url)

    def test_rejects_unsupported_prompt_type(self):
        result, requests = self.call(return_value=FakeResponse(text_payload()), prompt_or_contents=123)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Formato de prompt inválido")
        self.assertEqual(requests, [])

    def test_wraps_a_string_as_a_user_turn(self):
        _, requests = self.call(return_value=FakeResponse(text_payload()), prompt_or_contents="hola")
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertEqual(payload["contents"], [{"role": "user", "parts": [{"text": "hola"}]}])
        self.assertNotIn("systemInstruction", payload)
        self.assertNotIn("tools", payload)

    def test_forwards_an_explicit_contents_list(self):
        history = [
            {"role": "user", "parts": [{"text": "a"}]},
            {"role": "model", "parts": [{"text": "b"}]},
        ]
        _, requests = self.call(return_value=FakeResponse(text_payload()), prompt_or_contents=history)
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertEqual(payload["contents"], history)

    def test_adds_system_instruction_when_given(self):
        _, requests = self.call(return_value=FakeResponse(text_payload()),
                                prompt_or_contents="x", system_instruction="sos un arquitecto")
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertEqual(payload["systemInstruction"], {"parts": [{"text": "sos un arquitecto"}]})

    def test_uses_default_tool_declarations_when_enabled(self):
        _, requests = self.call(return_value=FakeResponse(text_payload()),
                                prompt_or_contents="x", enable_tools=True)
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertEqual(payload["tools"], TOOL_DECLARATIONS)

    def test_custom_tool_declarations_win(self):
        custom = [{"name": "solo_esta"}]
        _, requests = self.call(return_value=FakeResponse(text_payload()),
                                prompt_or_contents="x", enable_tools=True,
                                tool_declarations=custom)
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertEqual(payload["tools"], custom)

    def test_tool_declarations_are_ignored_when_tools_are_disabled(self):
        _, requests = self.call(return_value=FakeResponse(text_payload()),
                                prompt_or_contents="x", tool_declarations=[{"name": "x"}])
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertNotIn("tools", payload)

    def test_posts_json_to_the_requested_model(self):
        _, requests = self.call(return_value=FakeResponse(text_payload()),
                                prompt_or_contents="x", model="gemini-2.5-pro")
        request = requests[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("/models/gemini-2.5-pro:generateContent", request.full_url)
        self.assertEqual(request.get_header("Content-type"), "application/json")

    def test_trims_a_long_history_before_sending_it(self):
        history = [{"role": "user", "parts": [{"text": "inicio"}]}]
        for _ in range(10):
            history.append({"role": "model", "parts": [{"text": "m"}]})
            history.append({"role": "function", "parts": [{"text": "f"}]})

        _, requests = self.call(return_value=FakeResponse(text_payload()), prompt_or_contents=history)
        payload = json.loads(requests[0].data.decode("utf-8"))
        self.assertLessEqual(len(payload["contents"]), gemini_client.CONTENTS_LIMIT)
        self.assertEqual(payload["contents"][0]["role"], "user")
        self.assertEqual(payload["contents"][0]["parts"][0]["text"], "inicio")


class TestGenerateContentResponses(GeminiCase):

    def test_returns_plain_text(self):
        result, _ = self.call(return_value=FakeResponse(text_payload("respuesta")),
                              prompt_or_contents="x")
        self.assertEqual(result, {"ok": True, "is_tool_call": False,
                                  "text": "respuesta", "model_used": "gemini-2.5-flash"})

    def test_joins_every_text_part(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "uno "}, {"text": "dos"}]}}]}
        result, _ = self.call(return_value=FakeResponse(payload), prompt_or_contents="x")
        self.assertEqual(result["text"], "uno dos")

    def test_ignores_parts_that_are_not_objects(self):
        payload = {"candidates": [{"content": {"parts": ["basura", {"text": "ok"}]}}]}
        result, _ = self.call(return_value=FakeResponse(payload), prompt_or_contents="x")
        self.assertEqual(result["text"], "ok")

    def test_reports_a_function_call(self):
        result, _ = self.call(
            return_value=FakeResponse(tool_payload("read_file", {"path": "openapi.yaml"})),
            prompt_or_contents="x",
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["is_tool_call"])
        self.assertEqual(result["tool_name"], "read_file")
        self.assertEqual(result["tool_args"], {"path": "openapi.yaml"})
        self.assertEqual(result["raw_parts"], [{"functionCall": {"name": "read_file",
                                                                "args": {"path": "openapi.yaml"}}}])

    def test_finds_a_function_call_after_a_text_part(self):
        """El modelo puede anteponer texto: el functionCall no siempre es parts[0]."""
        result, _ = self.call(return_value=FakeResponse(tool_payload(prefix_text="voy a leer")),
                              prompt_or_contents="x")
        self.assertTrue(result["is_tool_call"])
        self.assertEqual(result["tool_name"], "read_file")

    def test_empty_candidates_is_an_error(self):
        result, _ = self.call(return_value=FakeResponse({"candidates": []}), prompt_or_contents="x")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Respuesta vacía del modelo")

    def test_missing_content_defaults_to_empty_text(self):
        payload = {"candidates": [{"finishReason": "SAFETY"}]}
        result, _ = self.call(return_value=FakeResponse(payload), prompt_or_contents="x")
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "")


class TestGenerateContentErrors(GeminiCase):

    def test_non_retryable_http_error_is_returned_immediately(self):
        result, requests = self.call(
            side_effect=[http_error(400, b"bad request")],
            prompt_or_contents="x",
        )
        self.assertFalse(result["ok"])
        self.assertIn("HTTP 400", result["error"])
        self.assertIn("bad request", result["error"])
        self.assertEqual(len(requests), 1)

    def test_retryable_codes_rotate_to_the_next_model(self):
        """El modelo pedido encabeza la lista; el segundo es el primer fallback distinto."""
        for code in (429, 503, 404):
            result, requests = self.call(
                side_effect=[http_error(code, b"cuota"), FakeResponse(text_payload("ok"))],
                prompt_or_contents="x",
                model="gemini-2.5-flash",
            )
            self.assertTrue(result["ok"], code)
            self.assertEqual(result["model_used"], gemini_client.FALLBACK_MODELS[1])
            self.assertEqual(len(requests), 2)
            self.assertIn("gemini-2.5-flash-lite", requests[1].full_url)

    def test_exhausting_every_model_returns_the_last_http_error(self):
        # El modelo por defecto ya está en FALLBACK_MODELS: no se repite.
        attempts = len(gemini_client.FALLBACK_MODELS)
        result, requests = self.call(
            side_effect=[http_error(429, f"intento-{i}".encode()) for i in range(attempts)],
            prompt_or_contents="x",
        )
        self.assertFalse(result["ok"])
        self.assertEqual(len(requests), attempts)
        self.assertIn("HTTP 429", result["error"])
        self.assertIn(f"intento-{attempts - 1}", result["error"])

    def test_connection_errors_are_reported_without_retrying(self):
        result, requests = self.call(
            side_effect=[urllib.error.URLError("sin red")],
            prompt_or_contents="x",
        )
        self.assertFalse(result["ok"])
        self.assertIn("sin red", result["error"])
        self.assertEqual(len(requests), 1)

    def test_error_body_is_truncated(self):
        result, _ = self.call(side_effect=[http_error(400, b"x" * 1000)], prompt_or_contents="x")
        self.assertLess(len(result["error"]), 320)

    def test_a_requested_model_is_not_tried_twice(self):
        attempts = len(gemini_client.FALLBACK_MODELS)
        _, requests = self.call(
            side_effect=[http_error(429, b"x") for _ in range(attempts)],
            prompt_or_contents="x",
            model=gemini_client.FALLBACK_MODELS[0],
        )
        urls = [request.full_url for request in requests]
        self.assertEqual(len(urls), len(set(urls)))


class TestTrimContents(unittest.TestCase):

    def test_short_history_is_returned_as_a_copy(self):
        contents = [{"role": "user", "parts": []}]
        trimmed = gemini_client._trim_contents(contents)
        self.assertEqual(trimmed, contents)
        self.assertIsNot(trimmed, contents)

    def test_exactly_at_the_limit_is_untouched(self):
        contents = [{"role": "model", "parts": []} for _ in range(gemini_client.CONTENTS_LIMIT)]
        trimmed = gemini_client._trim_contents(contents)
        self.assertEqual(len(trimmed), gemini_client.CONTENTS_LIMIT)
        self.assertEqual(trimmed, contents)

    def test_drops_every_tool_response_left_orphaned_at_the_cut(self):
        contents = [{"role": "user", "parts": [{"text": "inicio"}]}]
        # El corte cae justo antes de dos respuestas de herramienta consecutivas.
        contents += [{"role": "model", "parts": []} for _ in range(8)]
        contents += [{"role": "function", "parts": []}, {"role": "function", "parts": []}]
        contents += [{"role": "model", "parts": []}, {"role": "model", "parts": []}]

        trimmed = gemini_client._trim_contents(contents, limit=12, keep=4)
        self.assertEqual(trimmed[0]["role"], "user")
        self.assertNotEqual(trimmed[1]["role"], "function")
        self.assertTrue(all(item["role"] == "model" for item in trimmed[1:]))

    def test_history_of_only_tool_responses_keeps_the_head(self):
        contents = [{"role": "user", "parts": []}] + [
            {"role": "function", "parts": []} for _ in range(6)
        ]
        trimmed = gemini_client._trim_contents(contents, limit=2, keep=3)
        self.assertEqual(trimmed, [contents[0]])


class TestToolsLoopExtras(unittest.TestCase):
    """Casos del bucle autónomo que test_tools.py no cubre."""

    def setUp(self):
        self.calls = []
        self.original = gemini_client.generate_content
        self.addCleanup(setattr, gemini_client, "generate_content", self.original)

    def _patch(self, responses):
        queue = list(responses)

        def fake(contents, **kwargs):
            self.calls.append({"contents": contents, **kwargs})
            return queue.pop(0)

        gemini_client.generate_content = fake

    def test_model_error_is_returned_untouched(self):
        self._patch([{"ok": False, "error": "cuota agotada"}])
        result = gemini_client.run_with_tools_loop("x")
        self.assertEqual(result, {"ok": False, "error": "cuota agotada"})

    def test_always_enables_tools_and_defaults_the_registry(self):
        self._patch([{"ok": True, "is_tool_call": False, "text": "ok"}])
        gemini_client.run_with_tools_loop("x", system_instruction="sys")

        call = self.calls[0]
        self.assertTrue(call["enable_tools"])
        self.assertEqual(call["tool_declarations"], TOOL_DECLARATIONS)
        self.assertEqual(call["system_instruction"], "sys")
        self.assertEqual(call["contents"][0]["role"], "user")

    def test_custom_declarations_are_forwarded(self):
        self._patch([{"ok": True, "is_tool_call": False, "text": "ok"}])
        gemini_client.run_with_tools_loop("x", declarations=[{"name": "n"}] * 2)
        self.assertEqual(len(self.calls[0]["tool_declarations"]), 2)

    def test_tool_raising_type_error_is_reported_to_the_model(self):
        def broken(**kwargs):
            raise TypeError("falta path")

        self._patch([
            {"ok": True, "is_tool_call": True, "tool_name": "read_file",
             "tool_args": {"otra": 1}, "raw_parts": []},
            {"ok": True, "is_tool_call": False, "text": "ok"},
        ])
        gemini_client.run_with_tools_loop("x", tools={"read_file": broken})

        response = self.calls[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]
        self.assertFalse(response["ok"])
        self.assertIn("Argumentos inválidos para read_file", response["error"])
        self.assertIn("falta path", response["error"])

    def test_tool_raising_any_other_error_is_reported_to_the_model(self):
        def broken(**kwargs):
            raise RuntimeError("explotó")

        self._patch([
            {"ok": True, "is_tool_call": True, "tool_name": "read_file",
             "tool_args": {}, "raw_parts": []},
            {"ok": True, "is_tool_call": False, "text": "ok"},
        ])
        gemini_client.run_with_tools_loop("x", tools={"read_file": broken})

        response = self.calls[1]["contents"][-1]["parts"][0]["functionResponse"]["response"]
        self.assertEqual(response, {"ok": False, "error": "explotó"})

    def test_missing_tool_args_default_to_empty(self):
        seen = {}

        def tool(**kwargs):
            seen.update(kwargs)
            return {"ok": True}

        self._patch([
            {"ok": True, "is_tool_call": True, "tool_name": "noop", "raw_parts": []},
            {"ok": True, "is_tool_call": False, "text": "ok"},
        ])
        gemini_client.run_with_tools_loop("x", tools={"noop": tool})
        self.assertEqual(seen, {})

    def test_a_broken_trace_callback_does_not_stop_the_loop(self):
        def broken_step(**kwargs):
            raise RuntimeError("traza rota")

        self._patch([
            {"ok": True, "is_tool_call": True, "tool_name": "noop", "raw_parts": []},
            {"ok": True, "is_tool_call": False, "text": "terminó igual"},
        ])
        result = gemini_client.run_with_tools_loop(
            "x", tools={"noop": lambda: {"ok": True}}, on_step=broken_step
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "terminó igual")


if __name__ == "__main__":
    unittest.main()
