"""
Registro de tools disponibles.

Dos sets distintos, y la diferencia importa:

- `AVAILABLE_TOOLS`   todas las funciones implementadas.
- `AVAILABLE_AGENT_TOOLS`  las que un agente autónomo puede invocar de verdad.
"""

from .files import tool_list_dir, tool_read_file, tool_write_doc, tool_write_file
from .shell import tool_run_command

AVAILABLE_TOOLS = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "list_dir": tool_list_dir,
    "run_command": tool_run_command,
}

AGENT_TOOL_NAMES = ("read_file", "list_dir", "write_doc")

AVAILABLE_AGENT_TOOLS = {
    "read_file": tool_read_file,
    "list_dir": tool_list_dir,
    "write_doc": tool_write_doc,
}
