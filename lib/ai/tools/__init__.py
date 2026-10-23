"""
Tools de ejecución real para los agentes de Chelo-Harness.

Este paquete reexporta la superficie pública para que el resto del código siga
importando desde `lib.ai.tools`, sin conocer la división interna:

    paths.py -> lib/core/paths.py   sandbox de rutas (compartido con el MCP)
    files.py         read_file / list_dir / write_file / write_doc
    shell.py         run_command
    registry.py      qué tools existen y cuáles puede usar un agente
    declarations.py  esquemas JSON que se envían a Gemini
"""

from .declarations import AGENT_TOOL_DECLARATIONS, TOOL_DECLARATIONS
from .files import DOCS_DIR, tool_list_dir, tool_read_file, tool_write_doc, tool_write_file
from .registry import AGENT_TOOL_NAMES, AVAILABLE_AGENT_TOOLS, AVAILABLE_TOOLS
from .shell import tool_run_command

__all__ = [
    "AGENT_TOOL_DECLARATIONS",
    "AGENT_TOOL_NAMES",
    "AVAILABLE_AGENT_TOOLS",
    "AVAILABLE_TOOLS",
    "DOCS_DIR",
    "TOOL_DECLARATIONS",
    "tool_list_dir",
    "tool_read_file",
    "tool_run_command",
    "tool_write_doc",
    "tool_write_file",
]
