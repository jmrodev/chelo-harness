"""
Tools de archivos expuestas al modelo.

Cada función devuelve un dict con `ok`, nunca lanza: el resultado se manda
literalmente como `functionResponse` a Gemini.
"""

from pathlib import Path

from lib.core.paths import read_text, resolve_within, workspace_root, write_text

DOCS_DIR = "docs"


def tool_read_file(path: str) -> dict:
    return read_text(path, workspace_root())


def tool_list_dir(path: str = ".") -> dict:
    root = workspace_root()
    target = resolve_within(path, root)
    if target is None:
        return {"ok": False, "error": f"Ruta fuera del workspace: {path}"}
    if not target.is_dir():
        return {"ok": False, "error": f"Directorio no encontrado: {path}"}
    try:
        entries = sorted(
            str(item.relative_to(root))
            for item in target.iterdir()
            if not item.name.startswith(".")
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "entries": entries}


def tool_write_file(path: str, content: str) -> dict:
    """Escritura general, confinada al workspace. No la usan los agentes."""
    root = workspace_root()
    target = resolve_within(path, root)
    if target is None:
        return {"ok": False, "error": f"Ruta fuera del workspace: {path}"}
    return write_text(target, content, root, str(path))


def tool_write_doc(path: str, content: str) -> dict:
    """
    Escritura confinada a `docs/`. Es la única escritura de los agentes.

    Tolera el prefijo redundante ('docs/x.md' y 'x.md' apuntan al mismo lugar),
    porque los modelos alternan entre las dos formas.
    """
    root = workspace_root()
    docs = (root / DOCS_DIR).resolve()
    raw = str(path or "").strip()

    if not raw:
        return {"ok": False, "error": f"Falta la ruta del archivo (debe estar dentro de {DOCS_DIR}/)."}
    if Path(raw).is_absolute() or raw.startswith("~"):
        return {"ok": False, "error": f"Ruta absoluta rechazada: la escritura está confinada a {DOCS_DIR}/."}

    parts = [piece for piece in raw.replace("\\", "/").split("/") if piece not in ("", ".")]
    if parts and parts[0] == DOCS_DIR:
        parts = parts[1:]
    if not parts:
        return {"ok": False, "error": f"La ruta debe nombrar un archivo dentro de {DOCS_DIR}/."}

    target = docs.joinpath(*parts)
    return write_text(target, content, docs, f"{DOCS_DIR}/" + "/".join(parts))
