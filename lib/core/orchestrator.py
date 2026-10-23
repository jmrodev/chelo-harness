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

def _format_tool_args(args, limit=120):
    try:
        rendered = json.dumps(args or {}, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        rendered = str(args)
    return rendered if len(rendered) <= limit else rendered[:limit] + "…"


def _trace_tool_step(trace: bool):
    """Devuelve el callback de traza del bucle de tools (o None si no hay traza)."""
    if not trace:
        return None

    def callback(step, tool_name, tool_args, tool_result, **_):
        status = f"{GREEN}ok{NC}" if (tool_result or {}).get("ok") else f"{RED}error{NC}"
        log_trace(f"  paso {step + 1}: {BOLD}{tool_name}{NC}({_format_tool_args(tool_args)}) → {status}", True)

    return callback


def run_agent_turn(agent_role: str, user_instruction: str, context: str = "",
                   trace: bool = False, use_tools: bool = False, max_steps: int = 5):
    """
    Invoca a un agente específico mostrando traza en tiempo real si trace=True.

    Con `use_tools=True` el agente entra en el bucle de function calling: puede
    leer archivos del workspace, listar directorios y escribir dentro de docs/.
    Sin `use_tools` es una sola pasada de generación de texto.
    """
    system_prompt = get_agent_prompt(agent_role)
    log_trace(f"Cargando agente: '{agent_role}' (Directivas: {len(system_prompt)} bytes)", trace)

    full_prompt = (
        f"Directivas del rol:\n{system_prompt}\n\n"
        f"Contexto del workspace:\n{context}\n\n"
        f"Tarea requerida:\n{user_instruction}\n\n"
        f"IMPORTANTE: Devolvé ÚNICAMENTE el contenido del artefacto final sin prefacios ni explicaciones conversacionales."
    )

    t0 = time.time()
    if use_tools:
        from lib.ai.tools import AGENT_TOOL_DECLARATIONS, AVAILABLE_AGENT_TOOLS

        log_trace(
            f"Modo autónomo: tools = {', '.join(sorted(AVAILABLE_AGENT_TOOLS))} (máx. {max_steps} pasos)",
            trace,
        )
        resp = gemini_client.run_with_tools_loop(
            full_prompt,
            system_instruction=system_prompt,
            max_steps=max_steps,
            tools=AVAILABLE_AGENT_TOOLS,
            declarations=AGENT_TOOL_DECLARATIONS,
            on_step=_trace_tool_step(trace),
        )
    else:
        resp = gemini_client.generate_content(full_prompt, system_instruction=system_prompt)
    elapsed = time.time() - t0

    model_used = resp.get("model_used") or "desconocido"
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


def _agents_dir():
    """Ubica la carpeta de roles: repo actual, instalación o junto al módulo."""
    candidates = [
        Path.cwd() / "agents",
        Path.home() / ".local/lib/chelo/agents",
        Path(__file__).resolve().parent.parent.parent / "agents",
        Path(__file__).resolve().parent.parent / "agents",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def available_roles():
    directory = _agents_dir()
    return sorted(path.stem for path in directory.glob("*.md")) if directory else []


def _next_story_path():
    """Devuelve la próxima ruta libre docs/stories/US-NNN.md."""
    stories = Path.cwd() / "docs" / "stories"
    stories.mkdir(parents=True, exist_ok=True)
    highest = 0
    for path in stories.glob("US-*.md"):
        match = re.match(r"US-(\d+)", path.stem)
        if match:
            highest = max(highest, int(match.group(1)))
    return stories / f"US-{highest + 1:03d}.md"


def cmd_story():
    """Entrevista con el Story-Agent y escritura de la User Story BDD."""
    banner()
    check_git_repo()
    smooth_print(f"{BLUE}{BOLD}📝 Story-Agent (Product Owner) — modelado BDD{NC}\n", 0.05)

    requirement = input(f"{CYAN}👉 ¿Qué historia de usuario querés modelar? (o 'salir'):{NC} ").strip()
    if not requirement or requirement.lower() in ("salir", "exit", "quit", "q"):
        smooth_print(f"{YELLOW}Sin cambios.{NC}")
        return None

    smooth_print(f"\n{CYAN}▶ Invocando Story-Agent (BDD)...{NC}")
    response = run_agent_turn(
        "story-agent",
        f"Generá la User Story BDD en Markdown para: {requirement}. "
        "Estructura obligatoria: Rol, Acción, Beneficio, Escenarios Gherkin (Given/When/Then) "
        "y Lista Blanca de Endpoints requeridos.",
        trace=True,
    )
    if not response.get("ok"):
        smooth_print(f"{RED}❌ Error en Story-Agent: {response.get('error')}{NC}")
        return None

    content = strip_markdown_blocks(response.get("text", ""))
    target = _next_story_path()
    target.write_text(content, encoding="utf-8")
    smooth_print(f"{GREEN}✓ Historia escrita en {CYAN}{target.relative_to(Path.cwd())}{NC}\n", 0.05)
    render_markdown_smooth(content)
    return target


def cmd_agent(role):
    """Lanza un agente confinado con una tarea puntual."""
    banner()
    check_git_repo()

    if not role:
        roles = available_roles()
        smooth_print(f"{RED}Falta el rol.{NC} Disponibles: {', '.join(roles) or '(ninguno)'}")
        smooth_print(f"{CYAN}Uso:{NC} chelo-harness agent <rol>\n")
        return None

    if not get_agent_prompt(role):
        smooth_print(f"{RED}✗ Rol desconocido: {role}{NC}")
        smooth_print(f"{CYAN}Disponibles:{NC} {', '.join(available_roles())}\n")
        return None

    smooth_print(f"{BLUE}{BOLD}🤖 Agente confinado: {role}{NC}\n", 0.05)
    instruction = input(f"{CYAN}👉 Tarea para el agente (o 'salir'):{NC} ").strip()
    if not instruction or instruction.lower() in ("salir", "exit", "quit", "q"):
        smooth_print(f"{YELLOW}Sin cambios.{NC}")
        return None

    context = ""
    spec = Path.cwd() / "openapi.yaml"
    if spec.exists():
        context = spec.read_text(encoding="utf-8")

    smooth_print(f"\n{CYAN}▶ Ejecutando {role} en modo autónomo...{NC}")
    response = run_agent_turn(role, instruction, context=context, trace=True, use_tools=True)
    if not response.get("ok"):
        smooth_print(f"{RED}❌ Error en {role}: {response.get('error')}{NC}")
        return None

    render_markdown_smooth(response.get("text", ""))
    return response.get("text", "")

