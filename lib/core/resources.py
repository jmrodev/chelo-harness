"""
Dónde viven los recursos que acompañan al ejecutable.

Hoy: los roles de agente. Vive en `core` porque la comparten la CLI y el MCP, y
porque es una regla del arnés, no del modelo: importar esto no debe arrastrar el
cliente de Gemini ni la consola.

Antes había dos implementaciones con listas distintas, así que en una
instalación limpia la CLI no encontraba ningún rol y el MCP sí. Una sola lista,
un solo resultado.
"""

from pathlib import Path


def role_candidates(home=None, cwd=None, package_root=None):
    """
    Rutas a revisar para encontrar los roles, en orden de prioridad.

    - `agents/` del proyecto: permite override local.
    - `~/.local/share/chelo/agents`: donde los instala install.sh.
    - `agents/` junto al paquete: el repo durante el desarrollo.
    - `lib/agents`: layout intermedio.
    - `~/.local/lib/chelo/agents`: instalación vieja, por compatibilidad.
    """
    home = Path.home() if home is None else Path(home)
    cwd = Path.cwd() if cwd is None else Path(cwd)
    package_root = Path(__file__).resolve().parents[2] if package_root is None else Path(package_root)

    return [
        cwd / "agents",
        home / ".local" / "share" / "chelo" / "agents",
        package_root / "agents",
        package_root / "lib" / "agents",
        home / ".local" / "lib" / "chelo" / "agents",
    ]


def agents_dir(**kwargs):
    """Primer directorio de roles que exista, o None."""
    for candidate in role_candidates(**kwargs):
        if candidate.is_dir():
            return candidate
    return None


def available_roles(**kwargs):
    directory = agents_dir(**kwargs)
    return sorted(path.stem for path in directory.glob("*.md")) if directory else []
