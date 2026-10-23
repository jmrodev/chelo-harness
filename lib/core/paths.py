"""
Sandbox de rutas.

Única responsabilidad: decidir si una ruta puede tocarse y, si puede, leerla o
escribirla. Vive en `core` porque la comparten los tools de agentes y los
handlers del MCP: es una regla del arnés, no del modelo.

Toda ruta se resuelve con `resolve()` (sigue symlinks) y después se verifica
por contención real, así que `..`, rutas absolutas y enlaces que apunten afuera
se rechazan antes de tocar el disco.
"""

from pathlib import Path


def workspace_root():
    return Path.cwd().resolve()


def resolve_within(path, root):
    """
    Resuelve `path` relativo a `root` y verifica contención.

    Devuelve la ruta resuelta, o None si escapa del root.
    """
    raw = str(path or ".").strip() or "."
    if Path(raw).is_absolute() or raw.startswith("~"):
        return None
    resolved = (root / raw).resolve()
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


def read_text(path, root):
    target = resolve_within(path, root)
    if target is None:
        return {"ok": False, "error": f"Ruta fuera del workspace: {path}"}
    if not target.is_file():
        return {"ok": False, "error": f"Archivo no encontrado: {path}"}
    try:
        return {"ok": True, "content": target.read_text(encoding="utf-8")}
    except UnicodeDecodeError:
        return {"ok": False, "error": f"El archivo no es texto UTF-8: {path}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def write_text(target, content, root, shown):
    """Escribe `content` en `target`, verificando que quede dentro de `root`."""
    resolved = target.resolve()
    if resolved != root and root not in resolved.parents:
        return {"ok": False, "error": f"Ruta fuera de {root.name}/: {shown}"}
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return {"ok": True, "message": f"Archivo escrito exitosamente: {shown}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
