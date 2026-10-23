#!/usr/bin/env python3
"""
Startup check: verifica stack tecnológico y credenciales antes de iniciar la sesión.
"""

import os
import shutil
from pathlib import Path
from lib.ui.console import RED, GREEN, YELLOW, CYAN, BLUE, BOLD, NC, smooth_print
from lib.core.stack_detector import detect_workspace_stack

def check_credentials_and_stack(trace: bool = False):
    """
    Muestra el estado del workspace (stack detectado + credenciales disponibles)
    antes de iniciar cualquier sesión interactiva.
    Devuelve True si hay al menos una clave de IA configurada para continuar.
    """
    smooth_print(f"\n{BLUE}{BOLD}🔎 Analizando workspace...{NC}\n", 0.05)

    # --- STACK DETECTOR ---
    stack = detect_workspace_stack()

    smooth_print(f"  {CYAN}Stack detectado:{NC}")
    if stack["backend"]:
        smooth_print(f"    {GREEN}✓ Backend:{NC}  {stack['backend']}")
    if stack["frontend"]:
        smooth_print(f"    {GREEN}✓ Frontend:{NC} {stack['frontend']}")
    if stack["package_manager"]:
        smooth_print(f"    {GREEN}✓ Package Manager:{NC} {stack['package_manager']}")
    if stack["has_openapi"]:
        smooth_print(f"    {GREEN}✓ Contrato OpenAPI:{NC} detectado")
    else:
        smooth_print(f"    {YELLOW}○ Contrato OpenAPI:{NC} no encontrado (se creará con 'init')")
    if stack["has_hurl"]:
        smooth_print(f"    {GREEN}✓ Tests Hurl:{NC} detectados")
    else:
        smooth_print(f"    {YELLOW}○ Tests Hurl:{NC} no encontrados")
    if stack["has_docker"]:
        smooth_print(f"    {GREEN}✓ Docker:{NC} detectado")
    if not stack["backend"] and not stack["frontend"]:
        smooth_print(f"    {YELLOW}○ Stack:{NC} Proyecto vacío o sin archivos de dependencias reconocidos")

    # --- CREDENCIALES ---
    smooth_print(f"\n  {CYAN}Credenciales:{NC}")

    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    has_any_key = bool(gemini_key or anthropic_key or openai_key)

    if gemini_key and gemini_key != "DISABLED":
        smooth_print(f"    {GREEN}✓ Gemini API Key:{NC}    {gemini_key[:4]}...{gemini_key[-4:]}")
    else:
        smooth_print(f"    {YELLOW}○ Gemini API Key:{NC}    No configurada")

    if anthropic_key and anthropic_key != "DISABLED":
        smooth_print(f"    {GREEN}✓ Anthropic API Key:{NC} {anthropic_key[:4]}...{anthropic_key[-4:]}")
    else:
        smooth_print(f"    {YELLOW}○ Anthropic API Key:{NC} No configurada")

    if openai_key and openai_key != "DISABLED":
        smooth_print(f"    {GREEN}✓ OpenAI API Key:{NC}    {openai_key[:4]}...{openai_key[-4:]}")
    else:
        smooth_print(f"    {YELLOW}○ OpenAI API Key:{NC}    No configurada")

    # --- HERRAMIENTAS ---
    smooth_print(f"\n  {CYAN}Herramientas:{NC}")
    tools = {
        "prism": shutil.which("prism") or shutil.which("npx"),
        "hurl": shutil.which("hurl") or str(Path.home() / ".local/bin/hurl") if (Path.home() / ".local/bin/hurl").exists() else None,
        "gh": shutil.which("gh"),
    }
    for name, found in tools.items():
        if found:
            smooth_print(f"    {GREEN}✓ {name}:{NC} disponible")
        else:
            smooth_print(f"    {YELLOW}○ {name}:{NC} no detectado")

    if trace:
        smooth_print(f"\n  {CYAN}Motor de trazado:{NC} {YELLOW}ACTIVO{NC} — todas las llamadas a agentes y escrituras a disco serán visibles.\n")
    else:
        smooth_print("")

    if not has_any_key:
        smooth_print(f"\n{RED}❌ No hay ninguna API Key configurada. Ejecutá 'chelo-harness setup' antes de continuar.{NC}\n")
        return False

    return True
