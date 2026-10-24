#!/usr/bin/env python3
"""
Módulo cliente HTTP para Gemini API (Free Tier) con soporte para Function Calling y Tools loop.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from lib.ai.tools import AVAILABLE_TOOLS, TOOL_DECLARATIONS

FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest"
]

# Tope de turnos enviados al modelo. Se recorta por pares (model/function):
# cortar un `functionResponse` de su `functionCall` produce un 400 del API.
CONTENTS_LIMIT = 12
CONTENTS_KEEP = 10


def _trim_contents(contents, limit=CONTENTS_LIMIT, keep=CONTENTS_KEEP):
    """Recorta el historial sin dejar huérfana una respuesta de herramienta."""
    if len(contents) <= limit:
        return list(contents)

    head = contents[0]
    tail = list(contents[-keep:])
    while tail and tail[0].get("role") == "function":
        tail.pop(0)
    return [head] + tail


def generate_content(prompt_or_contents, system_instruction=None, model="gemini-2.5-flash",
                     enable_tools=False, tool_declarations=None):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"ok": False, "error": "Falta configurar GEMINI_API_KEY (ejecutá 'chelo-harness setup')"}

    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]

    if isinstance(prompt_or_contents, str):
        contents = [{"role": "user", "parts": [{"text": prompt_or_contents}]}]
    elif isinstance(prompt_or_contents, list):
        contents = list(prompt_or_contents)
    else:
        return {"ok": False, "error": "Formato de prompt inválido"}

    contents = _trim_contents(contents)

    payload = {"contents": contents}
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
    if enable_tools:
        payload["tools"] = tool_declarations if tool_declarations is not None else TOOL_DECLARATIONS

    data_bytes = json.dumps(payload).encode("utf-8")
    last_error = ""

    for current_model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if not candidates:
                    return {"ok": False, "error": "Respuesta vacía del modelo"}

                first_candidate = candidates[0].get("content", {})
                parts = first_candidate.get("parts", [{}])

                # El functionCall puede no venir en parts[0] (el modelo puede
                # anteponer un part de texto). Se busca en todo el turno.
                function_call = next(
                    (part["functionCall"] for part in parts if isinstance(part, dict) and "functionCall" in part),
                    None,
                )
                if function_call:
                    return {
                        "ok": True,
                        "is_tool_call": True,
                        "tool_name": function_call.get("name"),
                        "tool_args": function_call.get("args", {}),
                        "model_used": current_model,
                        "raw_parts": parts
                    }

                text = "".join(
                    part.get("text", "") for part in parts if isinstance(part, dict)
                )
                return {"ok": True, "is_tool_call": False, "text": text, "model_used": current_model}

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            last_error = f"HTTP {e.code}: {err_body[:300]}"
            if e.code in [429, 503, 404]:
                continue
            return {"ok": False, "error": last_error}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": last_error or "Error conectando con los modelos"}

def run_with_tools_loop(prompt: str, system_instruction: str = None, max_steps: int = 5,
                        tools=None, declarations=None, on_step=None):
    """
    Bucle autónomo: el modelo inspecciona, escribe y valida hasta terminar.

    `tools` limita qué funciones puede invocar realmente el modelo: una llamada
    a un nombre fuera de ese diccionario se devuelve como error al modelo, no se
    ejecuta. `on_step` recibe el detalle de cada paso para la traza.
    """
    registry = AVAILABLE_TOOLS if tools is None else tools
    declarations = TOOL_DECLARATIONS if declarations is None else declarations

    contents = [{"role": "user", "parts": [{"text": prompt}]}]

    for step in range(max_steps):
        resp = generate_content(
            contents,
            system_instruction=system_instruction,
            enable_tools=True,
            tool_declarations=declarations,
        )
        if not resp.get("ok"):
            return resp

        if not resp.get("is_tool_call"):
            return {"ok": True, "text": resp.get("text", ""), "model_used": resp.get("model_used")}

        t_name = resp.get("tool_name")
        t_args = resp.get("tool_args") or {}
        tool_fn = registry.get(t_name)

        if not tool_fn:
            tool_result = {"ok": False, "error": f"Herramienta no está habilitada: {t_name}"}
        else:
            try:
                tool_result = tool_fn(**t_args)
            except TypeError as exc:
                tool_result = {"ok": False, "error": f"Argumentos inválidos para {t_name}: {exc}"}
            except Exception as exc:  # noqa: BLE001
                tool_result = {"ok": False, "error": str(exc)}

        if on_step is not None:
            try:
                on_step(step=step, tool_name=t_name, tool_args=t_args, tool_result=tool_result)
            except Exception:  # noqa: BLE001 — una traza rota no corta el trabajo
                pass

        # Registrar el turno del modelo y la respuesta de la tool
        contents.append({"role": "model", "parts": resp.get("raw_parts", [])})
        contents.append({
            "role": "function",
            "parts": [{
                "functionResponse": {
                    "name": t_name,
                    "response": tool_result
                }
            }]
        })

    return {"ok": False, "error": f"Límite de pasos autónomos alcanzado ({max_steps})"}
