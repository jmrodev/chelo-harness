#!/usr/bin/env python3
"""
Módulo de ejecución de pruebas de contrato Hurl contra Prism Mock o Backend real.
"""

import os
import sys
import time
import socket
import shutil
import subprocess
from pathlib import Path
from lib.spec.mock_engine import find_openapi_spec, find_prism_runner, PRISM_PORT
from lib.ui.console import RED, GREEN, YELLOW, BOLD, NC, banner

def find_hurl_runner():
    """Detecta hurl en PATH o en ~/.local/bin/hurl."""
    if shutil.which("hurl"):
        return "hurl"
    user_hurl = Path.home() / ".local/bin/hurl"
    if user_hurl.is_file() and os.access(user_hurl, os.X_OK):
        return str(user_hurl)
    return None

def run_native_python_test(hurl_file):
    """Ejecutor HTTP mínimo de pruebas para archivos .hurl sin binario hurl."""
    import urllib.request
    import urllib.error
    
    try:
        content = hurl_file.read_text(encoding="utf-8")
        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
        if not lines:
            return True
            
        first_line = lines[0].split()
        method = first_line[0]
        url = first_line[1]
        
        req = urllib.request.Request(url, method=method)
        req.add_header("User-Agent", "CheloHarness-NativeTest/1.0")
        
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                status_code = response.getcode()
        except urllib.error.HTTPError as e:
            status_code = e.code

        expected_status = 200
        for l in lines:
            if l.startswith("HTTP"):
                parts = l.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    expected_status = int(parts[1])
                    break
                    
        return status_code == expected_status
    except Exception:
        return False

def execute_tests_and_collect_errors():
    """Ejecuta los tests y devuelve (passed, lista_errores)."""
    hurl_files = sorted(list(Path.cwd().glob("**/*.hurl")))
    if not hurl_files:
        return False, ["No se encontraron archivos de test .hurl en el repositorio."]

    mock_running = False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", PRISM_PORT)) == 0:
            mock_running = True

    mock_proc = None
    if not mock_running:
        spec = find_openapi_spec()
        runner = find_prism_runner()
        if spec and runner:
            mock_proc = subprocess.Popen(
                runner + ["mock", str(spec), "-p", str(PRISM_PORT)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.5)

    hurl_bin = find_hurl_runner()
    failed = 0
    errors = []

    for hf in hurl_files:
        print(f"   🧪 Testeando {hf.name}...", end=" ", flush=True)
        if hurl_bin:
            res = subprocess.run([hurl_bin, "--test", str(hf)], capture_output=True, text=True)
            passed = (res.returncode == 0)
            raw_err = (res.stderr or "").strip()
            filtered_lines = [
                line for line in raw_err.splitlines()
                if "no version information available" not in line
            ]
            err = "\n".join(filtered_lines).strip()
        else:
            passed = run_native_python_test(hf)
            err = "El status code o payload no coincidió con lo esperado."

        if passed:
            print(f"{GREEN}PASÓ ✓{NC}")
        else:
            print(f"{RED}FALLÓ ✗{NC}")
            failed += 1
            if err:
                print(f"{YELLOW}{err[:300]}{NC}")
                errors.append(f"Archivo: {hf.name}\nDetalle:\n{err}")

    if mock_proc:
        mock_proc.terminate()
        try:
            mock_proc.wait(timeout=2)
        except Exception:
            mock_proc.kill()

    if failed == 0:
        print(f"\n{GREEN}{BOLD}✓ TODAS LAS PRUEBAS SUPERADAS SIN VIOLACIONES DE CONTRATO.{NC}\n")
        return True, []
    else:
        print(f"\n{RED}{BOLD}❌ {failed} prueba(s) fallaron contra el contrato OpenAPI.{NC}\n")
        return False, errors

def cmd_test():
    banner()
    passed, _ = execute_tests_and_collect_errors()
    if not passed:
        sys.exit(1)
    return passed
