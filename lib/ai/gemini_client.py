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

def generate_content(prompt_or_contents, system_instruction=None, model="gemini-2.5-flash", enable_tools=False):
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

    if len(contents) > 12:
        contents = [contents[0]] + contents[-10:]

    payload = {"contents": contents}
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }
    if enable_tools:
        payload["tools"] = TOOL_DECLARATIONS

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
                
                # Chequear si el modelo pidió invocar una función (Tool Call)
                function_call = parts[0].get("functionCall")
                if function_call:
                    return {
                        "ok": True,
                        "is_tool_call": True,
                        "tool_name": function_call.get("name"),
                        "tool_args": function_call.get("args", {}),
                        "model_used": current_model,
                        "raw_parts": parts
                    }

                text = parts[0].get("text", "")
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

def run_with_tools_loop(prompt: str, system_instruction: str = None, max_steps: int = 5):
    """Bucle autónomo: el modelo puede inspeccionar, escribir y validar hasta terminar la tarea."""
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    
    for step in range(max_steps):
        resp = generate_content(contents, system_instruction=system_instruction, enable_tools=True)
        if not resp.get("ok"):
            return resp

        if not resp.get("is_tool_call"):
            return {"ok": True, "text": resp.get("text", "")}

        # Ejecutar herramienta local
        t_name = resp.get("tool_name")
        t_args = resp.get("tool_args", {})
        tool_fn = AVAILABLE_TOOLS.get(t_name)

        if not tool_fn:
            tool_result = {"ok": False, "error": f"Herramienta no implementada: {t_name}"}
        else:
            try:
                tool_result = tool_fn(**t_args)
            except Exception as e:
                tool_result = {"ok": False, "error": str(e)}

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
