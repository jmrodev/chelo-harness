"""
Infraestructura compartida por los handlers del MCP.

Nada de dominio acá: solo captura de salida, cambio de workspace, estado del
mock y utilidades de proceso. Cada handler importa lo que necesita de este
módulo y se olvida del resto.
"""

import contextlib
import io
import json
import os
import re
import socket
from pathlib import Path

LOG_LIMIT = 8000
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# lib/mcp/runtime.py -> lib/mcp -> lib -> raíz del paquete/repo
PKG_ROOT = Path(__file__).resolve().parents[2]

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "chelo-harness"
MOCK_STATE = STATE_DIR / "mock.json"
MOCK_LOG = STATE_DIR / "mock.log"


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
def clean(text):
    """Quita códigos ANSI: el cliente MCP no los renderiza."""
    return ANSI_RE.sub("", text or "").strip()


def clip(text, limit=LOG_LIMIT):
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "\n… (log truncado)"


def invoke(fn, *args, **kwargs):
    """
    Ejecuta código que imprime y devuelve `{"ok", "value", "log"}`.

    Necesario porque stdout es el canal JSON-RPC: si una librería imprime, el
    protocolo se corrompe. `redirect_stdout` lo desvía a un buffer.
    """
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            value = fn(*args, **kwargs)
    except SystemExit as exc:
        return {"ok": False, "error": f"El comando terminó con código {exc.code}", "log": clip(clean(buffer.getvalue()))}
    except Exception as exc:  # noqa: BLE001 — el servidor nunca debe caerse
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "log": clip(clean(buffer.getvalue()))}
    return {"ok": True, "value": value, "log": clip(clean(buffer.getvalue()))}


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def enter(args):
    """Cambia al workspace indicado y restaura el cwd al salir."""
    previous = Path.cwd()
    target = (args or {}).get("workspace")
    if target:
        candidate = Path(os.path.expanduser(str(target))).resolve()
        if candidate.is_dir():
            os.chdir(candidate)
    try:
        yield Path.cwd()
    finally:
        os.chdir(previous)


def agents_dir():
    """
    Ubica los roles de agente.

    En el repo viven en `<repo>/agents`; instalado viven en
    `~/.local/share/chelo/agents`. Probar ambos evita que el MCP instalado
    reporte una lista vacía.
    """
    for candidate in (
        PKG_ROOT / "agents",
        Path.home() / ".local/share/chelo/agents",
        Path.cwd() / "agents",
    ):
        if candidate.is_dir():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Procesos y puertos
# ---------------------------------------------------------------------------
def port_open(port, host="127.0.0.1", timeout=0.4):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def read_mock_state():
    try:
        return json.loads(MOCK_STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def write_mock_state(payload):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MOCK_STATE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_mock_state():
    try:
        MOCK_STATE.unlink()
    except Exception:  # noqa: BLE001
        pass
