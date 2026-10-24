"""
Ejecución de shell.

Queda fuera del set de agentes a propósito: ejecución arbitraria disparada por
un modelo no se habilita por defecto. Sigue disponible para uso explícito
(`AVAILABLE_TOOLS`), no para el bucle autónomo.
"""

import subprocess


def tool_run_command(cmd: str) -> dict:
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return {
            "ok": True,
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
