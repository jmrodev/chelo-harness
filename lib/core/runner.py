#!/usr/bin/env python3
"""
Módulo de detección y ejecución de runners de agentes externos (AGY, OpenCode).
"""

import os
import shutil
from pathlib import Path

def find_agent_runner():
    """Detecta el motor de IA preferido: Antigravity CLI (AGY) o fallback a OpenCode."""
    if shutil.which("agy") or (Path.home() / ".local/bin/agy").is_file():
        return "agy"
    if shutil.which("opencode") or (Path.home() / ".local/bin/opencode").is_file():
        return "opencode"
    return None

def find_opencode_runner():
    """Detecta opencode en PATH, ~/.opencode/bin o ~/.local/bin."""
    if shutil.which("opencode"):
        return "opencode"
    candidates = [
        Path.home() / ".opencode/bin/opencode",
        Path.home() / ".local/bin/opencode"
    ]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    return None

def get_agent_prompt(agent_name):
    """Carga las directivas de un agente desde agents/<agent_name>.md."""
    locations = [
        Path.cwd() / f"agents/{agent_name}.md",
        Path.home() / f".local/share/chelo-harness/agents/{agent_name}.md",
        Path(__file__).resolve().parent.parent.parent / f"agents/{agent_name}.md"
    ]
    for loc in locations:
        if loc.is_file():
            return loc.read_text(encoding="utf-8")
    return ""
