"""
Esquemas JSON que se envían a Gemini en `payload["tools"]`.

Separado de la implementación porque cambia por otro motivo: acá se ajusta el
contrato que ve el modelo (descripciones, tipos), no el código que ejecuta.
"""


def declaration(name, description, properties, required=None):
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "OBJECT",
            "properties": properties,
            **({"required": required} if required else {}),
        },
    }


_READ_PATH = {"path": {"type": "STRING", "description": "Ruta relativa del archivo dentro del workspace."}}
_WRITE_PATH = {"path": {"type": "STRING", "description": "Ruta relativa del archivo a escribir."}}
_CONTENT = {"type": "STRING", "description": "Contenido completo del archivo."}

TOOL_DECLARATIONS = [
    {
        "functionDeclarations": [
            declaration("read_file", "Lee el contenido completo de un archivo en el workspace.",
                        dict(_READ_PATH), ["path"]),
            declaration("write_file", "Crea o sobrescribe un archivo en el workspace.",
                        {**_WRITE_PATH, **{"content": _CONTENT}}, ["path", "content"]),
            declaration("list_dir", "Lista los archivos y carpetas dentro de un directorio relativo.",
                        {"path": {"type": "STRING", "description": "Directorio a listar (default '.')."}}),
            declaration("run_command", "Ejecuta un comando bash en el workspace (útil para tests o validaciones).",
                        {"cmd": {"type": "STRING", "description": "Comando de shell a ejecutar."}}, ["cmd"]),
        ]
    }
]

AGENT_TOOL_DECLARATIONS = [
    {
        "functionDeclarations": [
            declaration(
                "read_file",
                "Lee un archivo del workspace. Usalo para inspeccionar el contrato OpenAPI, historias o tests.",
                dict(_READ_PATH),
                ["path"],
            ),
            declaration(
                "list_dir",
                "Lista el contenido de un directorio del workspace.",
                {"path": {"type": "STRING", "description": "Directorio a listar (default '.')."}},
            ),
            declaration(
                "write_doc",
                "Escribe un archivo dentro de docs/. Es la única escritura permitida.",
                {
                    "path": {"type": "STRING", "description": "Ruta relativa dentro de docs/, ej: stories/US-001.md."},
                    "content": _CONTENT,
                },
                ["path", "content"],
            ),
        ]
    }
]
