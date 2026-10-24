"""
Transporte JSON-RPC 2.0 sobre stdio (especificación MCP 2024-11-05).

Este módulo no sabe qué hace cada tool: solo habla el protocolo.

Regla de oro: stdout es el canal del protocolo. Cualquier cosa que imprima una
librería tiene que pasar por `runtime.invoke`, que la desvía a un buffer.
"""

import io
import json
import sys

from .registry import TOOL_INDEX, TOOLS

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "chelo-harness", "version": "1.1.0"}

INSTRUCTIONS = (
    "Chelo-Harness expone gobernanza Spec-First: contrato OpenAPI, mock, tests Hurl, "
    "freno de 10 archivos, canales ágiles y agentes confinados. Empezá por chelo_status."
)


class _Sink(io.TextIOBase):
    """Sumidero para que nada externo corrompa el canal JSON-RPC."""

    def write(self, text):
        return len(text)

    def flush(self):
        return None


_PROTOCOL_OUT = sys.stdout
sys.stdout = _Sink()


def respond(payload):
    _PROTOCOL_OUT.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _PROTOCOL_OUT.flush()


def error(request_id, code, message):
    respond({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def _is_error_payload(payload):
    if not isinstance(payload, dict):
        return False
    if payload.get("passed") is False:
        return True
    if payload.get("ok") is False and "error" in payload:
        return True
    if payload.get("committed") is False:
        return True
    if payload.get("started") is False and payload.get("already_running") is not True:
        return True
    return "error" in payload and payload.get("ok") is not True


def call_tool(name, arguments):
    tool = TOOL_INDEX.get(name)
    if not tool:
        return {
            "content": [{"type": "text", "text": json.dumps({"error": f"Herramienta desconocida: {name}"})}],
            "isError": True,
        }

    try:
        payload = tool["handler"](arguments or {})
    except Exception as exc:  # noqa: BLE001 — un handler roto no debe tumbar el server
        payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return {
        "content": [{"type": "text", "text": json.dumps(payload, indent=2, ensure_ascii=False)}],
        "isError": _is_error_payload(payload),
    }


def _initialize(request_id, params):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "serverInfo": SERVER_INFO,
            "capabilities": {"tools": {"listChanged": False}},
            "instructions": INSTRUCTIONS,
        },
    }


def _tools_list(request_id):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": [
                {"name": tool["name"], "description": tool["description"], "inputSchema": tool["inputSchema"]}
                for tool in TOOLS
            ]
        },
    }


def _tools_call(request_id, params):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": call_tool(params.get("name"), params.get("arguments")),
    }


def handle(request):
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return _initialize(request_id, params)
    if method == "tools/list":
        return _tools_list(request_id)
    if method == "tools/call":
        return _tools_call(request_id, params)
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            error(None, -32700, f"Parse error: {exc}")
            continue

        if "id" not in request or request.get("id") is None:
            continue  # Notificación: nunca se responde.

        try:
            respond(handle(request))
        except BrokenPipeError:
            break
        except Exception as exc:  # noqa: BLE001
            error(request.get("id"), -32603, f"Internal error: {exc}")
