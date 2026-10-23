#!/usr/bin/env python3
"""
Módulo orquestador de agentes de Chelo-Harness.
Ejecuta la cadena Spec-First: Lead-Architect -> Story-Agent -> Spec-Architect -> QA-Tester -> Devs.
"""

import os
import sys
import json
import time
from pathlib import Path
from lib.ui.console import RED, GREEN, YELLOW, CYAN, BLUE, MAGENTA, BOLD, NC, smooth_print, render_markdown_smooth, banner
from lib.core.gate import check_git_repo, audit_changes_rule
from lib.core.runner import find_agent_runner, get_agent_prompt
from lib.ai import gemini_client
from lib.spec.tester import execute_tests_and_collect_errors

def get_project_name():
    return Path.cwd().name

def run_agent_turn(agent_role: str, user_instruction: str, context: str = ""):
    """Invoca a un agente específico con su rol y directivas aisladas."""
    system_prompt = get_agent_prompt(agent_role)
    full_prompt = f"Directivas del rol:\n{system_prompt}\n\nContexto actual:\n{context}\n\nTarea requerida:\n{user_instruction}"
    return gemini_client.generate_content(full_prompt, system_instruction=system_prompt)

def run_pipeline(project_name: str, requirement: str):
    """Ejecuta el pipeline desacoplado paso a paso con agentes independientes."""
    smooth_print(f"\n{BOLD}{BLUE}⚙️  CHELO-HARNESS: Iniciando Pipeline Desacoplado...{NC}\n", 0.05)

    # 1. STORY-AGENT: BDD Gherkin
    smooth_print(f"  {CYAN}▶ [1/3] Disparando Story-Agent (BDD)...{NC}")
    story_resp = run_agent_turn("story-agent", f"Generá la User Story BDD en Markdown para: {requirement}. Incluí criterios Gherkin y endpoints requeridos.")
    story_content = story_resp.get("text", "")
    story_path = Path.cwd() / "docs/stories/US-001.md"
    story_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_text(story_content, encoding="utf-8")
    smooth_print(f"  {GREEN}✓ [Story-Agent]{NC} Documento generado en {CYAN}{story_path.name}{NC}")

    # 2. SPEC-ARCHITECT: OpenAPI 3.0 Contract
    smooth_print(f"  {CYAN}▶ [2/3] Disparando Spec-Architect (OpenAPI 3.0)...{NC}")
    spec_resp = run_agent_turn("spec-architect", "Generá la especificación openapi.yaml completa en YAML estricto basada en la historia.", context=story_content)
    spec_content = spec_resp.get("text", "")
    if spec_content.startswith("```"):
        import re
        spec_content = re.sub(r"^```[a-z]*\n", "", spec_content)
        spec_content = re.sub(r"\n```$", "", spec_content)
    spec_path = Path.cwd() / "openapi.yaml"
    spec_path.write_text(spec_content, encoding="utf-8")
    smooth_print(f"  {GREEN}✓ [Spec-Architect]{NC} Contrato generado en {CYAN}{spec_path.name}{NC}")

    # 3. QA-TESTER: Tests Hurl con aserción de contrato
    smooth_print(f"  {CYAN}▶ [3/3] Disparando QA-Tester (Tests Hurl)...{NC}")
    qa_resp = run_agent_turn("qa-tester", "Generá los tests de contrato Hurl contra http://localhost:4010 con aserciones sl-violations y status codes.", context=spec_content)
    qa_content = qa_resp.get("text", "")
    if qa_content.startswith("```"):
        import re
        qa_content = re.sub(r"^```[a-z]*\n", "", qa_content)
        qa_content = re.sub(r"\n```$", "", qa_content)
    hurl_path = Path.cwd() / "tests/001_contract.hurl"
    hurl_path.parent.mkdir(parents=True, exist_ok=True)
    hurl_path.write_text(qa_content, encoding="utf-8")
    smooth_print(f"  {GREEN}✓ [QA-Tester]{NC} Suite generada en {CYAN}{hurl_path.name}{NC}\n")

    # Verificación determinista de contrato
    smooth_print(f"{BOLD}{BLUE}🔍 Ejecutando verificación de contrato OpenAPI + Prism...{NC}\n", 0.05)
    passed, errors = execute_tests_and_collect_errors()
    if passed:
        smooth_print(f"\n{BOLD}{GREEN}🎉 Pipeline Spec-First completado exitosamente.{NC}")
    else:
        smooth_print(f"\n{YELLOW}⚠️  Se detectaron diferencias con el contrato. Revisar reporte superior.{NC}")

    audit_changes_rule()
