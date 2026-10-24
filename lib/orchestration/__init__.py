"""
Ejecución de agentes de Chelo-Harness.

    turn.py      un turno: prompt + modelo (+ bucle de tools si se pide)
    pipeline.py  la cadena Spec-First y sus reglas de corrección
    roles.py     dónde viven los roles y cuáles hay
    cli.py       los comandos interactivos story / agent

Este `__init__` reexporta la superficie pública para que el resto del código
importe desde `lib.orchestration` sin conocer la división interna.
"""

from .cli import cmd_agent, cmd_story
from .pipeline import get_project_name, run_pipeline
from .roles import available_roles, agents_dir
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
