"""
Ejecución de agentes de Chelo-Harness.

    turn.py      un turno: prompt + modelo (+ bucle de tools si se pide)
    pipeline.py  la cadena Spec-First y sus reglas de corrección
    cli.py       los comandos interactivos story / agent

Los roles no viven acá: su ubicación es `lib.core.resources`, compartida con el
MCP para que las dos superficies no puedan volver a discrepar.

Este `__init__` reexporta la superficie pública para que el resto del código
importe desde `lib.orchestration` sin conocer la división interna.
"""

from lib.core.resources import agents_dir, available_roles

from .cli import cmd_agent, cmd_story
from .pipeline import get_project_name, run_pipeline
from .turn import log_trace, run_agent_turn, strip_markdown_blocks

__all__ = [
    "agents_dir",
    "available_roles",
    "cmd_agent",
    "cmd_story",
    "get_project_name",
    "log_trace",
    "run_agent_turn",
    "run_pipeline",
    "strip_markdown_blocks",
]
