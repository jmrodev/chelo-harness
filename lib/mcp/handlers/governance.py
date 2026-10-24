"""
Handlers de gobernanza: estado, disyuntor de cambios, quality gate y commit.

Todos comparten una idea: medir el workspace contra las reglas de Chelo y
negarse a avanzar cuando la regla se rompe.
"""

import re
import subprocess

from ..runtime import enter, invoke, port_open


def h_status(args):
    with enter(args) as root:
        from lib.core.gate import MAX_ALLOWED_CHANGES, get_git_status
        from lib.core.stack_detector import detect_workspace_stack
        from lib.spec.mock_engine import PRISM_PORT, find_openapi_spec

        is_git = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True
        ).returncode == 0
        count, files = get_git_status() if is_git else (0, [])
        spec = find_openapi_spec()
        hurl = sorted(str(path.relative_to(root)) for path in root.glob("**/*.hurl"))

        return {
            "workspace": str(root),
            "project": root.name,
            "is_git_repo": is_git,
            "modified_files": count,
            "limit": MAX_ALLOWED_CHANGES,
            "within_limit": count <= MAX_ALLOWED_CHANGES,
            "files": files,
            "spec": str(spec.relative_to(root)) if spec else None,
            "contract_tests": hurl,
            "mock_port": PRISM_PORT,
            "mock_running": port_open(PRISM_PORT),
            "stack": detect_workspace_stack(),
        }


def h_audit_changes(args):
    with enter(args):
        from lib.core.gate import MAX_ALLOWED_CHANGES, get_git_status

        count, files = get_git_status()
        return {
            "modified_files_count": count,
            "is_safe": count <= MAX_ALLOWED_CHANGES,
            "limit": MAX_ALLOWED_CHANGES,
            "files": files,
        }


def h_quality_gate(args):
    with enter(args):
        from lib.core.gate import MAX_ALLOWED_CHANGES, get_git_status
        from lib.spec.tester import execute_tests_and_collect_errors

        count, files = get_git_status()
        if count > MAX_ALLOWED_CHANGES:
            return {
                "passed": False,
                "stage": "contencion",
                "message": f"Freno de contención: {count} archivos modificados (límite {MAX_ALLOWED_CHANGES}).",
                "files": files,
            }

        result = invoke(execute_tests_and_collect_errors)
        if not result["ok"]:
            return {"passed": False, "stage": "tests", "error": result["error"], "log": result["log"]}

        passed, errors = result["value"]
        return {
            "passed": passed,
            "stage": "tests",
            "modified_files": count,
            "errors": errors,
            "log": result["log"],
        }


FORBIDDEN_ATTRIBUTION = [
    (r"co-authored-by", "atribución Co-Authored-By"),
    (r"\bai\b", "atribución de IA"),
    (r"generated with", "atribución de IA"),
    (r"🤖", "atribución de IA"),
]

CONVENTIONAL_COMMIT = re.compile(r"^[a-z]+(\([a-z0-9\-_.]+\))?!?: .+")


def h_commit(args):
    with enter(args):
        from lib.core.gate import MAX_ALLOWED_CHANGES, get_git_status

        message = (args.get("message") or "").strip()
        if not message:
            return {"committed": False, "error": "Falta 'message'."}

        lowered = message.lower()
        for pattern, reason in FORBIDDEN_ATTRIBUTION:
            if re.search(pattern, lowered):
                return {"committed": False, "error": f"Mensaje rechazado por gobernanza: {reason}."}

        if not CONVENTIONAL_COMMIT.match(message):
            return {
                "committed": False,
                "error": "El mensaje debe ser Conventional Commits, ej: feat(game): add orbital physics.",
            }

        count, files = get_git_status()
        if count == 0:
            return {"committed": False, "error": "No hay cambios para commitear."}
        if count > MAX_ALLOWED_CHANGES:
            return {
                "committed": False,
                "error": f"Freno de contención: {count} archivos (límite {MAX_ALLOWED_CHANGES}).",
                "files": files,
            }

        subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
        commit = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
        if commit.returncode != 0:
            return {"committed": False, "error": (commit.stderr or commit.stdout).strip()}

        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        return {
            "committed": True,
            "message": message,
            "files": files,
            "commit": head.stdout.strip(),
        }
