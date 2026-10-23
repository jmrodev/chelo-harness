#!/usr/bin/env python3
"""
chelo_gemini_client.py — Cliente directo HTTP para Gemini API (Free Tier)
Permite a chelo-harness invocar al modelo Gemini Flash gratis sin depender de ninguna CLI externa.
"""

import os
import sys
import json
import urllib.request
import urllib.error

FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
    "gemini-flash-lite-latest"
]

def generate_content(prompt_or_contents, system_instruction=None, model="gemini-2.5-flash"):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"ok": False, "error": "Falta configurar GEMINI_API_KEY (ejecutá 'chelo-harness setup')"}

    # Determinar secuencia de modelos a probar (el solicitado + fallbacks)
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]
    
    if isinstance(prompt_or_contents, str):
        contents = [{"role": "user", "parts": [{"text": prompt_or_contents}]}]
    elif isinstance(prompt_or_contents, list):
        contents = prompt_or_contents
    else:
        return {"ok": False, "error": "Formato de prompt inválido"}

    if isinstance(contents, list) and len(contents) > 10:
        # Mantener el primer turno (setup) y los últimos 8 turnos
        contents = [contents[0]] + contents[-8:]

    payload = {"contents": contents}
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    data_bytes = json.dumps(payload).encode("utf-8")

    last_error = ""
    for current_model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                candidates = res_json.get("candidates", [])
                if candidates:
                    text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    return {"ok": True, "text": text, "model_used": current_model}
                return {"ok": False, "error": "Respuesta vacía del modelo"}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore")
            last_error = f"HTTP {e.code}: {err_body[:300]}"
            # Si es 429 (Rate Limit) o 503 (Overloaded) o 404, rotar automáticamente al siguiente modelo
            if e.code in [429, 503, 404]:
                continue
            return {"ok": False, "error": last_error}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": last_error or "Todos los modelos fallaron por límite de cuota (429)"}

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "di solo 'ok'"
    res = generate_content(p)
    print(res)
