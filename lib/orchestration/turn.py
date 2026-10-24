"""
Un turno de agente.

Convierte (rol, instrucción, contexto) en una respuesta del modelo. No sabe qué
es un pipeline ni cómo se invoca desde la CLI: si querés cambiar cómo se arma el
prompt o cuándo se entra al bucle de tools, este es el único archivo.
"""

import json
import re
import time

from lib.ai import gemini_client
from lib.core.runner import get_agent_prompt
from lib.ui.console import BOLD, GREEN, MAGENTA, NC, RED


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
