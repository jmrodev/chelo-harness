#!/usr/bin/env python3
"""
Módulo de interfaz de consola y formateo ANSI para Chelo-Harness.
"""

import sys
import shutil
import subprocess
import time

CYAN = "\033[0;36m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
BLUE = "\033[0;34m"
MAGENTA = "\033[0;35m"
BOLD = "\033[1m"
NC = "\033[0m"

def render_markdown_smooth(text):
    """Renderiza Markdown con formato rico ANSI, resaltado de sintaxis y tablas."""
    try:
        from rich.console import Console
        from rich.markdown import Markdown
        from rich.panel import Panel
        console = Console()
        console.print(Panel(Markdown(text), border_style="cyan", title="[bold cyan]🧙 Lead-Architect[/bold cyan]"))
    except ImportError:
        if shutil.which("bat"):
            p = subprocess.Popen(["bat", "--language=markdown", "--style=plain", "--paging=never"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text)
        else:
            print(text)

def stream_typewriter(text, char_delay=0.002, line_delay=0.05):
    """Efecto suave de máquina de escribir sin bloquear eternamente."""
    lines = text.split("\n")
    for line in lines:
        for char in line:
            sys.stdout.write(char)
            sys.stdout.flush()
            if char in [".", ",", "!", "?"]:
                time.sleep(char_delay * 3)
            else:
                time.sleep(char_delay)
        sys.stdout.write("\n")
        sys.stdout.flush()
        time.sleep(line_delay)

def smooth_print(text="", delay=0.05):
    print(text)
    time.sleep(delay)

def banner():
    print(f"""{CYAN}{BOLD}
   ██████╗██╗  ██╗███████╗██╗      ██████╗ 
  ██╔════╝██║  ██║██╔════╝██║     ██╔═══██╗
  ██║     ███████║█████╗  ██║     ██║   ██║
  ██║     ██╔══██║██╔══╝  ██║     ██║   ██║
  ╚██████╗██║  ██║███████╗███████╗╚██████╔╝
   ╚═════╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ 
        🛡️ CHELO-HARNESS v1.0.0
   Gobernanza Spec-First y Coding-Agent
{NC}""")

def prompt_text(label, default=""):
    d_str = f" [{default}]" if default else ""
    val = input(f"{CYAN}{label}{d_str}:{NC} ").strip()
    return val if val else default
