"""
Resolución de credenciales.

Única pieza que sabe de dónde salen los secretos: entorno, `.env` cercano o el
`.env` central de prácticas. Slack y GitHub la usan; ninguno de los dos sabe
cómo se resuelve.
"""

import os
from pathlib import Path


def get_secret(key, default=None):
    """Obtiene credenciales desde variables de entorno, .env local, o secrets centrales."""
    # 1. Variables de entorno activas
    if os.environ.get(key):
        return os.environ.get(key)

    # 2. Archivo .env en el directorio actual o padres
    curr = Path.cwd()
    for parent in [curr] + list(curr.parents)[:3]:
        env_file = parent / ".env"
        if env_file.exists():
            try:
                with open(env_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() == key:
                                return v.strip().strip('"').strip("'")
            except Exception:
                pass

    # 3. Fallback a la ubicación de InstituteProjects2026
    inst_env = Path.home() / "Documents/Academy/TECDA/TERCERO/Practicas_profesionalizantes/InstituteProjects2026/.env"
    if inst_env.exists():
        try:
            with open(inst_env, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == key:
                            return v.strip().strip('"').strip("'")
        except Exception:
            pass

    return default
