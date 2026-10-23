#!/usr/bin/env python3
"""
Módulo de setup, configuración y diagnósticos del arnés.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from lib.ui.console import RED, GREEN, YELLOW, CYAN, BLUE, BOLD, NC, banner, smooth_print
from lib.spec.mock_engine import find_prism_runner
from lib.spec.tester import find_hurl_runner
from lib.core.runner import find_opencode_runner

def save_key_to_shells(var_name, key_val):
    """Persiste una variable en los archivos de shell del usuario y en el proceso actual."""
    os.environ[var_name] = key_val
    home = Path.home()
    
    bashrc = home / ".bashrc"
    if bashrc.exists():
        lines = bashrc.read_text(encoding="utf-8", errors="ignore").splitlines()
        filtered = [l for l in lines if not l.startswith(f"export {var_name}=")]
        filtered.append(f'export {var_name}="{key_val}"')
        bashrc.write_text("\n".join(filtered) + "\n", encoding="utf-8")

    zshrc = home / ".zshrc"
    if zshrc.exists():
        lines = zshrc.read_text(encoding="utf-8", errors="ignore").splitlines()
        filtered = [l for l in lines if not l.startswith(f"export {var_name}=")]
        filtered.append(f'export {var_name}="{key_val}"')
        zshrc.write_text("\n".join(filtered) + "\n", encoding="utf-8")

    fish_secrets = home / ".config/fish/conf.d/secrets.fish"
    if fish_secrets.parent.exists():
        lines = fish_secrets.read_text(encoding="utf-8", errors="ignore").splitlines() if fish_secrets.exists() else []
        filtered = [l for l in lines if not l.startswith(f"set -gx {var_name} ")]
        filtered.append(f"set -gx {var_name} '{key_val}'")
        fish_secrets.write_text("\n".join(filtered) + "\n", encoding="utf-8")

def cmd_setup():
    banner()
    print(f"{BLUE}🔑 ASISTENTE UNIVERSAL DE CONFIGURACIÓN DE CLAVES (SETUP){NC}\n")
    print("Podés configurar o indicar que no vas a usar un proveedor.\n")

    current_gemini = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if current_gemini and current_gemini != "DISABLED":
        print(f"  {GREEN}✓ Google Gemini API Key detectada:{NC} {current_gemini[:4]}...{current_gemini[-4:]}")
    else:
        print(f"\n{CYAN}--- GOOGLE GEMINI (Modelos gratuitos) ---{NC}")
        print(f"🔗 Clave gratis en: {BOLD}{YELLOW}https://aistudio.google.com/app/apikey{NC}")
        val = input(f"👉 Pegá tu clave [o Enter para omitir]: ").strip()
        if val:
            save_key_to_shells("GEMINI_API_KEY", val)
            save_key_to_shells("GOOGLE_GENERATIVE_AI_API_KEY", val)
            print(f"   {GREEN}✓ Google Gemini configurado.{NC}")

def cmd_doctor():
    banner()
    print(f"{BLUE}🔍 CHEQUEO DE ENTORNO, HERRAMIENTAS Y CLAVES (DOCTOR){NC}\n")

    hurl_runner = find_hurl_runner()
    if hurl_runner:
        print(f"  {GREEN}✓ Hurl:{NC} Instalado y listo ({hurl_runner}).")
    else:
        print(f"  {YELLOW}○ Hurl no detectado.{NC}")

    if shutil.which("gh") or (Path.home() / ".local/bin/gh").is_file():
        print(f"  {GREEN}✓ GitHub CLI (gh):{NC} Instalado.")
    else:
        print(f"  {YELLOW}○ GitHub CLI (gh) no detectado.{NC}")

    opencode_bin = find_opencode_runner()
    if opencode_bin:
        print(f"  {GREEN}✓ OpenCode CLI:{NC} Instalado y listo ({opencode_bin}).")
    else:
        print(f"  {YELLOW}○ OpenCode no detectado.{NC}")

    prism_runner = find_prism_runner()
    if prism_runner:
        print(f"  {GREEN}✓ Prism:{NC} Disponible ({' '.join(prism_runner)}) para OpenAPI.")
    else:
        print(f"  {GREEN}✓ Mock Server Nativo:{NC} Disponible en Python puro.")

    keys = {
        "GEMINI_API_KEY / GOOGLE_API_KEY": os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"),
        "SLACK_BOT_TOKEN": os.environ.get("SLACK_BOT_TOKEN"),
        "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY"),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY")
    }
    print(f"\n{CYAN}🔑 Estado de API Keys detectadas en el entorno:{NC}")
    for k, val in keys.items():
        if val:
            print(f"  {GREEN}✓ {k}:{NC} Configurada ({val[:4]}...{val[-4:] if len(val)>8 else ''})")
        else:
            print(f"  {YELLOW}○ {k}:{NC} No configurada")
    print("")
