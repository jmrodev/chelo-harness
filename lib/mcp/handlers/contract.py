"""
Handlers de contrato: lectura del OpenAPI y ejecución de la suite Hurl.
"""

from pathlib import Path

from ..runtime import enter, invoke

_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def parse_openapi_paths(text):
    """
    Extrae rutas y métodos con un parser de indentación best-effort.

    No es un parser YAML completo: solo alcanza para listar endpoints sin traer
    una dependencia externa.
    """
    paths = {}
    current = None

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip())
        line = stripped

        if indent == 2 and line.startswith("/") and line.endswith(":"):
            current = line[:-1].strip()
            paths[current] = []
        elif indent == 4 and current and line.endswith(":") and line[:-1].lower() in _METHODS:
            paths[current].append(line[:-1].upper())
        elif indent <= 2 and not line.startswith("/") and line.rstrip(":") != "paths":
            current = None

    return paths


def _spec_path(spec, root):
    """
    Resuelve el contrato y exige que quede dentro del workspace.

    El contrato autodetectado suele venir como ruta absoluta, así que acá no se
    rechazan las absolutas: se verifica contención.
    """
    path = Path(spec)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if path != root and root not in path.parents:
        return None
    return path


def h_spec_read(args):
    with enter(args) as root:
        from lib.spec.mock_engine import find_openapi_spec

        spec = args.get("path") or find_openapi_spec()
        if not spec:
            return {"found": False, "error": "No hay openapi.yaml en el workspace. Usá chelo_init."}

        path = _spec_path(spec, root)
        if path is None:
            return {"found": False, "error": f"Ruta fuera del workspace: {spec}"}
        if not path.is_file():
            return {"found": False, "error": f"Archivo inexistente: {path}"}

        text = path.read_text(encoding="utf-8")
        return {
            "found": True,
            "path": str(path),
            "bytes": len(text),
            "endpoints": parse_openapi_paths(text),
            "content": text if args.get("include_content") else None,
        }


def h_contract_test(args):
    with enter(args):
        from lib.spec.tester import execute_tests_and_collect_errors

        result = invoke(execute_tests_and_collect_errors)
        if not result["ok"]:
            return {"passed": False, "error": result["error"], "log": result["log"]}

        passed, errors = result["value"]
        return {"passed": passed, "errors": errors, "log": result["log"]}
