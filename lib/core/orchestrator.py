#!/usr/bin/env python3
"""
Módulo orquestador de agentes de Chelo-Harness.
Ejecuta la cadena Spec-First con soporte para modo verbose/auditoría (--test-trace).
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

def log_trace(msg: str, trace_enabled: bool = False):
    if trace_enabled:
        print(f"  {MAGENTA}[TRACE/AUDITORÍA]{NC} {msg}")

def run_agent_turn(agent_role: str, user_instruction: str, context: str = "", trace: bool = False):
    """Invoca a un agente específico mostrando traza en tiempo real si trace=True."""
    system_prompt = get_agent_prompt(agent_role)
    log_trace(f"Cargando agente: '{agent_role}' (Directivas: {len(system_prompt)} bytes)", trace)
    
    full_prompt = (
        f"Directivas del rol:\n{system_prompt}\n\n"
        f"Contexto del workspace:\n{context}\n\n"
        f"Tarea requerida:\n{user_instruction}\n\n"
        f"IMPORTANTE: Devolvé ÚNICAMENTE el contenido del artefacto final sin prefacios ni explicaciones conversacionales."
    )
    
    t0 = time.time()
    resp = gemini_client.generate_content(full_prompt, system_instruction=system_prompt)
    elapsed = time.time() - t0
    
    model_used = resp.get("model_used", "desconocido")
    chars_received = len(resp.get("text", "")) if resp.get("ok") else 0
    log_trace(f"Respuesta de Gemini recibida en {elapsed:.2f}s | Modelo: {model_used} | Tamaño: {chars_received} chars", trace)
    
    return resp

def run_pipeline(project_name: str, requirement: str, trace: bool = False):
    """Ejecuta el pipeline desacoplado mostrando con certeza cada función y llamada."""
    smooth_print(f"\n{BOLD}{BLUE}⚙️  CHELO-HARNESS: Iniciando Pipeline Spec-First...{NC}", 0.05)
    if trace:
        smooth_print(f"{MAGENTA}{BOLD}🔍 MODO AUDITORÍA / TEST-TRACE ACTIVO{NC}: Inspección en vivo de llamadas y agentes sin simulación.\n", 0.05)

    # 1. STORY-AGENT: BDD Gherkin
    smooth_print(f"  {CYAN}▶ [1/3] Invocando Story-Agent (BDD)...{NC}")
    story_resp = run_agent_turn(
        "story-agent",
        f"Generá la User Story BDD en Markdown para: {requirement}. "
        f"Estructura obligatoria: Rol, Acción, Beneficio, Escenarios Gherkin (Given/When/Then) y Lista Blanca de Endpoints requeridos.",
        trace=trace
    )
    if not story_resp.get("ok"):
        smooth_print(f"  {RED}❌ Error en Story-Agent: {story_resp.get('error')}{NC}")
        return

    story_content = strip_markdown_blocks(story_resp.get("text", ""))
    story_path = Path.cwd() / "docs/stories/US-001.md"
    story_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_text(story_content, encoding="utf-8")
    log_trace(f"Escrito en disco: {story_path} ({len(story_content)} bytes)", trace)
    smooth_print(f"  {GREEN}✓ [Story-Agent]{NC} User Story escrita en {CYAN}{story_path.relative_to(Path.cwd())}{NC}")

    # 2. SPEC-ARCHITECT: OpenAPI 3.0 Contract
    smooth_print(f"  {CYAN}▶ [2/3] Invocando Spec-Architect (OpenAPI 3.0)...{NC}")
    spec_resp = run_agent_turn(
        "spec-architect",
        "Diseñá la especificación openapi.yaml completa en YAML estricto cumpliendo la User Story. "
        "No uses bloque servers para evitar descalces. Incluí /health y schemas con examples para cada respuesta.",
        context=story_content,
        trace=trace
    )
    if not spec_resp.get("ok"):
        smooth_print(f"  {RED}❌ Error en Spec-Architect: {spec_resp.get('error')}{NC}")
        return

    spec_content = strip_markdown_blocks(spec_resp.get("text", ""))
    spec_path = Path.cwd() / "openapi.yaml"
    spec_path.write_text(spec_content, encoding="utf-8")
    log_trace(f"Escrito en disco: {spec_path} ({len(spec_content)} bytes)", trace)
    smooth_print(f"  {GREEN}✓ [Spec-Architect]{NC} Contrato escrito en {CYAN}openapi.yaml{NC}")

    # 3. QA-TESTER: Tests Hurl con aserción de contrato
    smooth_print(f"  {CYAN}▶ [3/3] Invocando QA-Tester (Tests Hurl)...{NC}")
    qa_resp = run_agent_turn(
        "qa-tester",
        "Escribí los tests de contrato Hurl contra http://localhost:4010 para cada endpoint del contrato OpenAPI. "
        "Obligatorio: incluir aserción `header \"sl-violations\" not exists` y asserts de status code.",
        context=spec_content,
        trace=trace
    )
    if not qa_resp.get("ok"):
        smooth_print(f"  {RED}❌ Error en QA-Tester: {qa_resp.get('error')}{NC}")
        return

    qa_content = strip_markdown_blocks(qa_resp.get("text", ""))
    hurl_path = Path.cwd() / "tests/001_contract.hurl"
    hurl_path.parent.mkdir(parents=True, exist_ok=True)
    hurl_path.write_text(qa_content, encoding="utf-8")
    log_trace(f"Escrito en disco: {hurl_path} ({len(qa_content)} bytes)", trace)
    smooth_print(f"  {GREEN}✓ [QA-Tester]{NC} Suite escrita en {CYAN}{hurl_path.relative_to(Path.cwd())}{NC}\n")

    # 4. Verificación de Contrato
    smooth_print(f"{BOLD}{BLUE}🔍 Ejecutando verificación real de contrato (Hurl + Prism)...{NC}", 0.05)
    log_trace("Llamando a execute_tests_and_collect_errors() en lib/spec/tester.py", trace)
    passed, errors = execute_tests_and_collect_errors()

    if not passed:
        # Clasificar el tipo de falla para enviar al agente correcto
        err_report = "\n".join(errors)
        is_hurl_syntax_error = any(
            kw in err_report for kw in ["Parsing predicate", "expecting a predicate", "Parsing error", "Invalid"]
        )
        is_contract_violation = "sl-violations" in err_report
        is_bad_assertion = any(
            kw in err_report for kw in ["Assert status code", "Assert failure", "actual value is", "actual:"]
        )

        if is_hurl_syntax_error or is_bad_assertion:
            smooth_print(f"\n{YELLOW}🔄 Aserciones/sintaxis incorrectas — enviando al QA-Tester para corrección...{NC}\n", 0.05)
            log_trace(f"Tipo de falla: {'SINTAXIS HURL' if is_hurl_syntax_error else 'ASERCIÓN INCORRECTA'}. Agente: qa-tester", trace)
            fix_resp = run_agent_turn(
                "qa-tester",
                f"Los tests Hurl fallaron con este reporte:\n{err_report}\n\n"
                f"Reescribí TODOS los tests corrigiendo status codes y valores esperados para que coincidan "
                f"exactamente con los examples del openapi.yaml. "
                f"Usá solo sintaxis Hurl válida: exists, ==, isInteger. NUNCA 'is defined'.",
                context=f"Contrato OpenAPI actual:\n{spec_content}",
                trace=trace
            )
            if fix_resp.get("ok"):
                fixed_hurl = strip_markdown_blocks(fix_resp.get("text", ""))
                hurl_path.write_text(fixed_hurl, encoding="utf-8")
                log_trace(f"Tests Hurl corregidos en disco ({len(fixed_hurl)} bytes)", trace)
                smooth_print(f"  {CYAN}✓ [QA-Tester]{NC} Tests corregidos. Re-probando...")
                passed, _ = execute_tests_and_collect_errors()
        elif is_contract_violation:
            smooth_print(f"\n{YELLOW}🔄 Violación de contrato detectada — enviando al Spec-Architect para reconciliación...{NC}\n", 0.05)
            log_trace(f"Tipo de falla: VIOLACIÓN DE CONTRATO. Agente corrector: spec-architect", trace)
            fix_resp = run_agent_turn(
                "spec-architect",
                f"El test de contrato falló contra Prism con este error:\n{err_report}\n\n"
                f"Corregí el openapi.yaml para que los examples y schemas coincidan con lo que Prism devuelve.",
                context=f"Historia:\n{story_content}\n\nOpenAPI actual:\n{spec_content}",
                trace=trace
            )
            if fix_resp.get("ok"):
                fixed_spec = strip_markdown_blocks(fix_resp.get("text", ""))
                spec_path.write_text(fixed_spec, encoding="utf-8")
                log_trace(f"Contrato reescrito en disco ({len(fixed_spec)} bytes)", trace)
                smooth_print(f"  {CYAN}✓ [Spec-Architect]{NC} Contrato reconciliado. Re-probando...")
                passed, _ = execute_tests_and_collect_errors()

    if passed:
        smooth_print(f"\n{BOLD}{GREEN}🎉 Pipeline Spec-First completado: Contrato válido y libre de violaciones.{NC}\n")
    else:
        smooth_print(f"\n{RED}❌ No se pudo validar el contrato al 100%. Ver reporte superior.{NC}\n")

    audit_changes_rule()
