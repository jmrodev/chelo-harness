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

def generate_content(prompt_or_contents, system_instruction=None, model="gemini-2.5-flash"):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return {"ok": False, "error": "Falta configurar GEMINI_API_KEY (ejecutá 'chelo-harness setup')"}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    if isinstance(prompt_or_contents, str):
        contents = [{"role": "user", "parts": [{"text": prompt_or_contents}]}]
    elif isinstance(prompt_or_contents, list):
        contents = prompt_or_contents
    else:
        return {"ok": False, "error": "Formato de prompt inválido"}

    payload = {"contents": contents}
    
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            candidates = res_json.get("candidates", [])
            if candidates:
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return {"ok": True, "text": text}
            return {"ok": False, "error": "Respuesta vacía del modelo"}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        return {"ok": False, "error": f"HTTP {e.code}: {err_body[:300]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "di solo 'ok'"
    res = generate_content(p)
    print(res)
