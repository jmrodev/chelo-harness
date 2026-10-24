"""
Resolución de credenciales.

Orden de búsqueda:

    1. variables de entorno
    2. el archivo apuntado por CHELO_ENV_FILE
    3. .env en el cwd o hasta tres directorios hacia arriba
    4. ~/.config/chelo/.env

No hay rutas personales acá: la tuya se declara con CHELO_ENV_FILE, así que
podés apuntar a un .env que ya tenés sin copiar secretos de un lado a otro.
"""

import os
from pathlib import Path

ENV_VAR = "CHELO_ENV_FILE"
USER_CONFIG = Path.home() / ".config" / "chelo" / ".env"


def _candidate_files():
    """Archivos a revisar, en orden de prioridad."""
    override = os.environ.get(ENV_VAR)
    if override:
        yield Path(os.path.expanduser(override))

    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents)[:3]:
        yield parent / ".env"

    yield USER_CONFIG


def _read_from(path, key):
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                if name.strip() == key:
                    return value.strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001
        pass
    return None


def get_secret(key, default=None):
    """Primer valor encontrado para `key`, o `default`."""
    value = os.environ.get(key)
    if value:
        return value

    for path in _candidate_files():
        if path.is_file():
            found = _read_from(path, key)
            if found is not None:
                return found

    return default
