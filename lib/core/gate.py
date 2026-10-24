#!/usr/bin/env python3
"""
Módulo de Quality Gate y disyuntor de seguridad (regla de los 10 archivos).
"""

import sys
import subprocess
from pathlib import Path
from lib.ui.console import RED, GREEN, YELLOW, CYAN, BOLD, NC, smooth_print

MAX_ALLOWED_CHANGES = 10

def check_git_repo():
    """Verifica si es un repo git. Si no lo es, auto-inicializa el entorno Spec-First automáticamente."""
    res = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    if res.returncode != 0:
        smooth_print(f"{YELLOW}⚡ Workspace no inicializado con Git. Auto-inicializando entorno Spec-First...{NC}\n", 0.05)
        from lib.core.init_project import cmd_init
        cmd_init()

def get_git_status():
    res = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    files = [l for l in res.stdout.splitlines() if l.strip()]
    return len(files), files

def audit_changes_rule():
    """Freno de mano / Disyuntor: Si supera 10 modificaciones, pausar de inmediato."""
    count, files = get_git_status()
    if count > MAX_ALLOWED_CHANGES:
        smooth_print(f"\n{RED}{BOLD}🛑 [DISYUNTOR ACTIVADO] REGLA DE LOS {MAX_ALLOWED_CHANGES} CAMBIOS SUPERADA{NC}")
        smooth_print(f"{YELLOW}El agente intentó modificar {count} archivos en este ciclo:{NC}")
        for f in files:
            smooth_print(f"  {RED}• {f}{NC}")
        smooth_print(f"\n{YELLOW}⚠️  Pausa obligatoria para evitar abarcar más de lo pedido en el ticket.{NC}")
        smooth_print(f"{CYAN}Revisá los cambios con 'git diff' o hacé un commit atómico antes de seguir.{NC}\n")
        return False
    return True
