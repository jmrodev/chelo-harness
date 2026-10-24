"""
Handlers del mock del contrato.

El mock corre como proceso en segundo plano (Prism si está, servidor nativo de
Python si no) y su estado se guarda en `~/.local/state/chelo-harness/mock.json`.
Ningún handler bloquea esperando un `subprocess.run`.
"""

import json
import os
import signal
import subprocess
import sys
import time

from ..runtime import (
    MOCK_LOG,
    PKG_ROOT,
    STATE_DIR,
    clean,
    clear_mock_state,
    enter,
    port_open,
    read_mock_state,
    write_mock_state,
)

START_ATTEMPTS = 50
START_INTERVAL = 0.2
STOP_ATTEMPTS = 25


def _launch_command(spec, port):
    from lib.spec.mock_engine import find_prism_runner

    runner = find_prism_runner()
    if runner:
        return runner + ["mock", str(spec), "-p", str(port)], "prism"

    code = (
        "import sys; sys.path.insert(0, " + json.dumps(str(PKG_ROOT)) + "); "
        "from pathlib import Path; "
        "from lib.spec.mock_engine import run_native_python_mock; "
        "run_native_python_mock(Path(" + json.dumps(str(spec)) + "), " + str(port) + ")"
    )
    return [sys.executable, "-c", code], "python-native"


def _wait_until_ready(port, process):
    for _ in range(START_ATTEMPTS):
        if port_open(port):
            return True
        if process.poll() is not None:
            return False
        time.sleep(START_INTERVAL)
    return False


def h_mock_start(args):
    with enter(args) as root:
        from lib.spec.mock_engine import PRISM_PORT, find_openapi_spec

        port = int(args.get("port") or PRISM_PORT)
        if port_open(port):
            return {"started": False, "already_running": True, "port": port, "url": f"http://localhost:{port}"}

        spec = find_openapi_spec()
        if not spec:
            return {"started": False, "error": "No hay contrato OpenAPI en el workspace. Usá chelo_init primero."}

        STATE_DIR.mkdir(parents=True, exist_ok=True)
        command, engine = _launch_command(spec, port)

        with open(MOCK_LOG, "a", encoding="utf-8") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=str(root),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

        if not _wait_until_ready(port, process):
            if process.poll() is None:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            tail = ""
            try:
                tail = clean(MOCK_LOG.read_text(encoding="utf-8"))[-1500:]
            except Exception:  # noqa: BLE001
                pass
            return {
                "started": False,
                "error": "El mock no respondió en el puerto esperado.",
                "engine": engine,
                "command": command,
                "log_tail": tail,
            }

        write_mock_state({
            "pid": process.pid,
            "pgid": process.pid,
            "port": port,
            "engine": engine,
            "spec": str(spec),
            "workspace": str(root),
        })
        return {
            "started": True,
            "engine": engine,
            "pid": process.pid,
            "port": port,
            "url": f"http://localhost:{port}",
            "spec": str(spec),
            "log_file": str(MOCK_LOG),
        }


def h_mock_stop(args):
    state = read_mock_state()
    if not state:
        return {"stopped": False, "message": "No hay mock registrado por chelo."}

    pid = state.get("pid")
    port = state.get("port")
    killed = _terminate(pid)

    for _ in range(STOP_ATTEMPTS):
        if not port_open(port):
            break
        time.sleep(0.2)

    clear_mock_state()
    return {"stopped": True, "signalled": killed, "pid": pid, "port": port, "port_still_open": port_open(port)}


def _terminate(pid):
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        return True
    except Exception:  # noqa: BLE001
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except Exception:  # noqa: BLE001
            return False


def h_mock_status(args):
    from lib.spec.mock_engine import PRISM_PORT

    state = read_mock_state() or {}
    port = int(args.get("port") or state.get("port") or PRISM_PORT)
    pid = state.get("pid")

    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except Exception:  # noqa: BLE001
            alive = False

    return {
        "running": port_open(port),
        "port": port,
        "url": f"http://localhost:{port}",
        "managed": bool(state),
        "pid": pid,
        "pid_alive": alive,
        "engine": state.get("engine"),
        "spec": state.get("spec"),
    }
