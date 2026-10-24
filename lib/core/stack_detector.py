#!/usr/bin/env python3
"""
Módulo de detección de stack tecnológico del workspace.
"""

from pathlib import Path

from lib.spec.mock_engine import find_openapi_spec


def detect_workspace_stack(root_dir: Path = None) -> dict:
    cwd = root_dir or Path.cwd()
    stack = {
        "backend": None,
        "frontend": None,
        "package_manager": None,
        "has_openapi": False,
        "has_hurl": False,
        "has_docker": False
    }

    # OpenAPI & Hurl
    # La regla de "dónde está el contrato" vive en find_openapi_spec: si acá se
    # escribe otra, la sesión y `mock` contestan distinto sobre el mismo repo.
    if find_openapi_spec(cwd):
        stack["has_openapi"] = True
    if list(cwd.glob("**/*.hurl")):
        stack["has_hurl"] = True
    if (cwd / "Dockerfile").exists() or (cwd / "docker-compose.yml").exists():
        stack["has_docker"] = True

    # Node / JS / TS
    pkg_json = cwd / "package.json"
    if pkg_json.exists():
        stack["package_manager"] = "npm"
        if (cwd / "pnpm-lock.yaml").exists():
            stack["package_manager"] = "pnpm"
        elif (cwd / "yarn.lock").exists():
            stack["package_manager"] = "yarn"
        elif (cwd / "bun.lockb").exists() or (cwd / "bun.lock").exists():
            stack["package_manager"] = "bun"

        try:
            content = pkg_json.read_text(encoding="utf-8").lower()
            if "next" in content:
                stack["frontend"] = "Next.js"
            elif "react" in content:
                stack["frontend"] = "React"
            elif "vue" in content:
                stack["frontend"] = "Vue"
            elif "express" in content or "fastify" in content or "nest" in content:
                stack["backend"] = "Node.js (Express/Fastify/Nest)"
        except Exception:
            pass

    # Python
    if (cwd / "requirements.txt").exists() or (cwd / "pyproject.toml").exists() or (cwd / "Pipfile").exists():
        stack["backend"] = "Python (FastAPI/Flask/Django)"
        if (cwd / "pyproject.toml").exists():
            stack["package_manager"] = "poetry/pip"

    # Go
    if (cwd / "go.mod").exists():
        stack["backend"] = "Go"

    # Rust
    if (cwd / "Cargo.toml").exists():
        stack["backend"] = "Rust"

    return stack
