#!/usr/bin/env python3
"""
chelo_mcp.py — Punto de entrada del servidor MCP de Chelo-Harness.

Toda la implementación vive en `lib/mcp/`:

    protocol.py   transporte JSON-RPC por stdio
    registry.py   catálogo de tools (nombre, esquema, handler)
    runtime.py    captura de salida, cambio de workspace, estado del mock
    handlers/     lógica de cada grupo (gobernanza, contrato, mock, …)

Este archivo solo resuelve imports y arranca. Se mantiene porque es el comando
que registra el cliente MCP.
"""

import sys
from pathlib import Path

# Válido en el repo (<repo>/lib/chelo_mcp.py) y en la instalación
# (~/.local/lib/chelo/lib/chelo_mcp.py): en ambos casos el padre del padre es
# la raíz que contiene el paquete `lib`.
_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from lib.mcp.protocol import main  # noqa: E402 — debe correr después del bootstrap

if __name__ == "__main__":
    main()
