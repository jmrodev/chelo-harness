"""
Esquema de entrada de las tools MCP.

Todas las herramientas aceptan `workspace` para poder operar sobre otro repo
sin mover el cwd del servidor.
"""

WORKSPACE_PROP = {
    "type": "string",
    "description": "Ruta del repo a operar. Por defecto, el cwd del servidor.",
}


def schema(properties=None, required=None):
    props = dict(properties or {})
    props.setdefault("workspace", WORKSPACE_PROP)
    return {"type": "object", "properties": props, "required": required or []}
