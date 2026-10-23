#!/usr/bin/env python3
"""
Módulo orquestador de agentes de Chelo-Harness.
Ejecuta la cadena Spec-First: Lead-Architect -> Story-Agent -> Spec-Architect -> QA-Tester -> Devs
utilizando Function Calling y verificación determinista.
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from lib.ui.console import RED, GREEN, YELLOW, CYAN, BLUE, MAGENTA, BOLD, NC, smooth_print, render_markdown_smooth, banner
from lib.core.gate import check_git_repo, audit_changes_rule
from lib.core.runner import find_agent_runner, get_agent_prompt
from lib.ai import gemini_client
from lib.spec.tester import execute_tests_and_collect_errors

def get_project_name():
    return Path.cwd().name

def strip_markdown_blocks(text: str) -> str:
    """Remueve bloques ``` de inicio y fin si el modelo los incluye."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_\-]*\n", "", cleaned)
        cleaned = re.sub(r"\n```$", "", cleaned)
    return cleaned.strip()

def run_agent_turn(agent_role: str, user_instruction: str, context: str = ""):
    """Invoca a un agente específico con su rol y directivas aisladas."""
    system_prompt = get_agent_prompt(agent_role)
    full_prompt = (
        f"Directivas del rol:\n{system_prompt}\n\n"
        f"Contexto del workspace:\n{context}\n\n"
        f"Tarea requerida:\n{user_instruction}\n\n"
        f"IMPORTANTE: Devolvé ÚNICAMENTE el contenido del artefacto final sin prefacios ni explicaciones conversacionales."
    )
    return gemini_client.generate_content(full_prompt, system_instruction=system_prompt)

def run_pipeline(project_name: str, requirement: str):
    """Ejecuta el pipeline desacoplado paso a paso con agentes independientes y verificación estricta."""
    smooth_print(f"\n{BOLD}{BLUE}⚙️  CHELO-HARNESS: Iniciando Pipeline Desacoplado (Spec-First)...{NC}\n", 0.05)

    # 1. STORY-AGENT: BDD Gherkin
    smooth_print(f"  {CYAN}▶ [1/3] Disparando Story-Agent (BDD)...{NC}")
    story_resp = run_agent_turn(
        "story-agent",
        f"Generá la User Story BDD en Markdown para: {requirement}. "
        f"Estructura obligatoria: Rol, Acción, Beneficio, Escenarios Gherkin (Given/When/Then) y Lista Blanca de Endpoints requeridos."
    )
    if not story_resp.get("ok"):
        smooth_print(f"  {RED}❌ Error en Story-Agent: {story_resp.get('error')}{NC}")
        return

    story_content = strip_markdown_blocks(story_resp.get("text", ""))
    story_path = Path.cwd() / "docs/stories/US-001.md"
    story_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_text(story_content, encoding="utf-8")
    smooth_print(f"  {GREEN}✓ [Story-Agent]{NC} User Story generada en {CYAN}{story_path.relative_to(Path.cwd())}{NC}")

    # 2. SPEC-ARCHITECT: OpenAPI 3.0 Contract
    smooth_print(f"  {CYAN}▶ [2/3] Disparando Spec-Architect (OpenAPI 3.0)...{NC}")
    spec_resp = run_agent_turn(
        "spec-architect",
        "Diseñá la especificación openapi.yaml completa en YAML estricto cumpliendo la User Story. "
        "No uses bloque servers para evitar descalces. Incluí /health y schemas con examples para cada respuesta.",
        context=story_content
    )
    if not spec_resp.get("ok"):
        smooth_print(f"  {RED}❌ Error en Spec-Architect: {spec_resp.get('error')}{NC}")
        return

    spec_content = strip_markdown_blocks(spec_resp.get("text", ""))
    spec_path = Path.cwd() / "openapi.yaml"
    spec_path.write_text(spec_content, encoding="utf-8")
    smooth_print(f"  {GREEN}✓ [Spec-Architect]{NC} Contrato generado en {CYAN}openapi.yaml{NC}")

    # 3. QA-TESTER: Tests Hurl con aserción de contrato
    smooth_print(f"  {CYAN}▶ [3/3] Disparando QA-Tester (Tests Hurl)...{NC}")
    qa_resp = run_agent_turn(
        "qa-tester",
        "Escribí los tests de contrato Hurl contra http://localhost:4010 para cada endpoint del contrato OpenAPI. "
        "Obligatorio: incluir aserción `header \"sl-violations\" not exists` y asserts de status code.",
        context=spec_content
    )
    if not qa_resp.get("ok"):
        smooth_print(f"  {RED}❌ Error en QA-Tester: {qa_resp.get('error')}{NC}")
        return

    qa_content = strip_markdown_blocks(qa_resp.get("text", ""))
    hurl_path = Path.cwd() / "tests/001_contract.hurl"
    hurl_path.parent.mkdir(parents=True, exist_ok=True)
    hurl_path.write_text(qa_content, encoding="utf-8")
    smooth_print(f"  {GREEN}✓ [QA-Tester]{NC} Suite generada en {CYAN}{hurl_path.relative_to(Path.cwd())}{NC}\n")

    # 4. Verificación de Contrato
    smooth_print(f"{BOLD}{BLUE}🔍 Ejecutando verificación de contrato OpenAPI + Prism...{NC}\n", 0.05)
    passed, errors = execute_tests_and_collect_errors()

    # Bucle de auto-corrección determinista (Spec-Architect y QA) si hubo fallas
    if not passed:
        smooth_print(f"\n{YELLOW}🔄 Disparando reconciliación de contrato Spec-First...{NC}\n", 0.05)
        err_report = "\n".join(errors)
        fix_resp = run_agent_turn(
            "spec-architect",
            f"El test de contrato falló contra Prism con este error:\n{err_report}\n\n"
            f"Corregí el openapi.yaml para satisfacer las respuestas y schemas requeridos.",
            context=f"Historia:\n{story_content}\n\nOpenAPI actual:\n{spec_content}"
        )
        if fix_resp.get("ok"):
            fixed_spec = strip_markdown_blocks(fix_resp.get("text", ""))
            spec_path.write_text(fixed_spec, encoding="utf-8")
            smooth_print(f"  {CYAN}✓ [Spec-Architect]{NC} Contrato reconciliado. Re-probando...")
            passed, _ = execute_tests_and_collect_errors()

    if passed:
        smooth_print(f"\n{BOLD}{GREEN}🎉 Pipeline Spec-First completado: Contrato válido y libre de violaciones.{NC}\n")
    else:
        smooth_print(f"\n{RED}❌ No se pudo validar el contrato al 100%. Ver reporte superior.{NC}\n")

    audit_changes_rule()
