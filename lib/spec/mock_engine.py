#!/usr/bin/env python3
"""
Módulo del motor de mocks (Prism y fallback nativo en Python).
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from lib.ui.console import RED, GREEN, YELLOW, CYAN, BLUE, BOLD, NC, banner

PRISM_PORT = 4010
BACKEND_PORT = 8000

def find_openapi_spec():
    candidates = list(Path.cwd().glob("**/openapi.yaml")) + \
                 list(Path.cwd().glob("**/openapi.yml")) + \
                 list(Path.cwd().glob("**/api*.yaml"))
    return candidates[0] if candidates else None

def find_prism_runner():
    """Detecta el mejor runner disponible para Prism."""
    local_prism = Path.cwd() / "node_modules" / ".bin" / "prism"
    if local_prism.is_file() and os.access(local_prism, os.X_OK):
        return [str(local_prism)]
    if shutil.which("prism"):
        return ["prism"]
    if shutil.which("npx"):
        return ["npx", "--yes", "@stoplight/prism-cli@5"]
    return None

def run_native_python_mock(spec_path, port=PRISM_PORT):
    """Mock server nativo HTTP con Python estándar sin dependencias."""
    import http.server
    import socketserver

    print(f"{YELLOW}⚠️  Prism no disponible. Iniciando Servidor Mock Nativo en Python (Zero-Dependency)...{NC}")
    print(f"{GREEN}✓ Servidor simulado activo en:{NC} {BOLD}http://localhost:{port}{NC}")
    print(f"{YELLOW}Presioná Ctrl+C para detener el mock.{NC}\n")

    endpoints = {}
    try:
        content = spec_path.read_text(encoding="utf-8")
        current_path = None
        for line in content.splitlines():
            line_str = line.strip()
            if line_str.startswith("/") and line_str.endswith(":"):
                current_path = line_str[:-1]
                endpoints[current_path] = {}
            elif current_path and line_str in ["get:", "post:", "put:", "delete:", "patch:"]:
                current_method = line_str[:-1].upper()
                endpoints[current_path][current_method] = {"status": 200, "body": {"status": "ok", "mock": "python-native"}}
    except Exception as e:
        print(f"{YELLOW}Nota: parsing básico de OpenAPI: {e}{NC}")

    class MockHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self._handle_request("GET")

        def do_POST(self):
            self._handle_request("POST")

        def do_PUT(self):
            self._handle_request("PUT")

        def do_DELETE(self):
            self._handle_request("DELETE")

        def _handle_request(self, method):
            parsed_path = self.path.split("?")[0]
            matched = endpoints.get(parsed_path, {}).get(method)
            
            status = 200
            if parsed_path in ["/health", "/api/health"]:
                body = {"status": "healthy", "service": "chelo-harness-mock"}
            elif method == "POST":
                status = 201
                body = {"status": "created", "mock": True, "path": parsed_path}
            elif matched:
                status = matched["status"]
                body = matched["body"]
            else:
                body = {"message": f"Chelo Mock: {method} {parsed_path}", "status": "ok"}

            payload = json.dumps(body, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("x-mock-engine", "chelo-python-native")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            print(f"   {CYAN}[Mock HTTP]{NC} {self.command} {self.path} -> 200/201")

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), MockHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Servidor Mock detenido.{NC}")

def cmd_mock():
    banner()
    spec = find_openapi_spec()
    if not spec:
        print(f"{RED}❌ No se encontró archivo de especificación OpenAPI (*.yaml) en el repositorio.{NC}")
        print(f"{YELLOW}Tip: Ejecutá 'chelo-harness init' para crear tu openapi.yaml base.{NC}")
        sys.exit(1)

    runner = find_prism_runner()
    if runner:
        print(f"{BLUE}🚀 Levantando Prism Mock Server desde:{NC} {spec}")
        print(f"{GREEN}✓ Servidor simulado activo en:{NC} {BOLD}http://localhost:{PRISM_PORT}{NC}")
        print(f"{YELLOW}Presioná Ctrl+C para detener el mock.{NC}\n")
        cmd = runner + ["mock", str(spec), "-p", str(PRISM_PORT)]
        subprocess.run(cmd)
    else:
        run_native_python_mock(spec, PRISM_PORT)

def cmd_proxy(backend_url=f"http://localhost:{BACKEND_PORT}"):
    banner()
    spec = find_openapi_spec()
    if not spec:
        print(f"{RED}❌ No se encontró archivo OpenAPI (*.yaml) para validar el proxy.{NC}")
        sys.exit(1)

    runner = find_prism_runner()
    if runner:
        print(f"{BLUE}🛡️ Levantando Prism Proxy de Validación:{NC}")
        print(f"   • Contrato: {spec}")
        print(f"   • Backend Real: {backend_url}")
        print(f"   • Proxy Validador: {BOLD}http://localhost:{PRISM_PORT}{NC}\n")
        cmd = runner + ["proxy", str(spec), backend_url, "-p", str(PRISM_PORT), "--validate-request"]
        subprocess.run(cmd)
    else:
        print(f"{RED}❌ Error: Prism Proxy requiere Prism CLI o npx para validar el tráfico.{NC}")
        print(f"{YELLOW}Instalá Prism como dependencia del proyecto: npm install --save-dev @stoplight/prism-cli{NC}")
