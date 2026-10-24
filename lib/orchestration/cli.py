"""
Comandos interactivos: `story` y `agent <rol>`.

Capa fina: pide datos, llama al turno del agente e imprime. Si cambia la
experiencia de terminal, cambia este archivo y nada más.
"""

import re
from pathlib import Path

from lib.core.gate import check_git_repo
from lib.core.runner import get_agent_prompt
from lib.ui.console import BLUE, BOLD, CYAN, GREEN, NC, RED, YELLOW, banner, render_markdown_smooth, smooth_print

from .roles import available_roles
from .turn import run_agent_turn, strip_markdown_blocks


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
