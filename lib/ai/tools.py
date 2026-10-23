#!/usr/bin/env python3
"""
Módulo de herramientas de ejecución real para los agentes de Chelo-Harness.
"""

import subprocess
from pathlib import Path

def tool_read_file(path: str) -> dict:
    try:
        p = Path.cwd() / path
        if not p.is_file():
            return {"ok": False, "error": f"Archivo no encontrado: {path}"}
        return {"ok": True, "content": p.read_text(encoding="utf-8")}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def tool_write_file(path: str, content: str) -> dict:
    try:
        p = Path.cwd() / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"ok": True, "message": f"Archivo escrito exitosamente: {path}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def tool_list_dir(path: str = ".") -> dict:
    try:
        p = Path.cwd() / path
        if not p.is_dir():
            return {"ok": False, "error": f"Directorio no encontrado: {path}"}
        entries = [str(x.relative_to(Path.cwd())) for x in p.iterdir() if not x.name.startswith(".")]
        return {"ok": True, "entries": sorted(entries)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def tool_run_command(cmd: str) -> dict:
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return {
            "ok": True,
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

AVAILABLE_TOOLS = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "list_dir": tool_list_dir,
    "run_command": tool_run_command
}
