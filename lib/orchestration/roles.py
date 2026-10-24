"""
Dónde viven los roles de agente.

Cambia cuando se agrega un rol o cambia el layout de instalación, no cuando
cambia el pipeline. Por eso está separado.
"""

from pathlib import Path


def agents_dir():
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
    directory = agents_dir()
    return sorted(path.stem for path in directory.glob("*.md")) if directory else []
