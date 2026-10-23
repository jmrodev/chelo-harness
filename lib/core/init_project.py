#!/usr/bin/env python3
"""
Módulo de inicialización de repositorios bajo la metodología Spec-First.
"""

import sys
import shutil
import subprocess
from pathlib import Path
from lib.ui.console import RED, GREEN, YELLOW, CYAN, BLUE, BOLD, NC, banner, smooth_print

def cmd_init():
    banner()
    cwd = Path.cwd()
    smooth_print(f"{BLUE}Iniciando Chelo-Harness en:{NC} {cwd}\n", 0.1)

    # 1. Verificar git
    if not (cwd / ".git").exists():
        smooth_print(f"  {YELLOW}Inicializando repositorio git...{NC}", 0.05)
        subprocess.run(["git", "init"], check=True)

    # 2. Docs y directivas
    docs_dir = cwd / "docs"
    docs_dir.mkdir(exist_ok=True)
    stories_dir = docs_dir / "stories"
    stories_dir.mkdir(exist_ok=True)
    tests_dir = cwd / "tests"
    tests_dir.mkdir(exist_ok=True)

    # 3. openapi.yaml base
    openapi_file = cwd / "openapi.yaml"
    if not openapi_file.exists():
        openapi_content = f"""openapi: 3.0.3
info:
  title: API {cwd.name}
  version: 1.0.0
  description: Contrato sagrado Spec-First de {cwd.name}.
paths:
  /health:
    get:
      summary: Health check del servicio
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: healthy
"""
        openapi_file.write_text(openapi_content, encoding="utf-8")
        smooth_print(f"  {GREEN}✓ Contrato OpenAPI creado:{NC} openapi.yaml", 0.05)

    # 4. AGENTS.md
    agents_file = cwd / "AGENTS.md"
    if not agents_file.exists():
        agents_content = """# Reglas de Gobernanza Chelo-Harness (Spec-First)

## 1. PRINCIPIO SAGRADO: DESACOPLAMIENTO TOTAL
- El Backend y el Frontend NO se comunican directamente en etapa de diseño ni se esperan para desarrollar.
- La ÚNICA fuente de verdad compartida es `openapi.yaml`.
- El Frontend consume `http://localhost:4010` (Prism Mock Server).
- El Backend implementa la lógica contra `:8000` validada por `chelo-harness test`.

## 2. RESTRICCIÓN DE ENDPOINTS
- Todo endpoint DEBE provenir de un User Story formal en `docs/stories/*.md` y de sus criterios BDD (Given/When/Then).

## 3. LÍMITE DE CONTENCIÓN
- Máximo 10 archivos modificados por ticket (Freno de seguridad del Quality Gate).
"""
        agents_file.write_text(agents_content, encoding="utf-8")
        smooth_print(f"  {GREEN}✓ Constitución de gobernanza creada:{NC} AGENTS.md", 0.05)

    # 5. Test Hurl base
    test_file = tests_dir / "000_health.hurl"
    if not test_file.exists():
        test_content = """GET http://localhost:4010/health
HTTP 200
[Asserts]
header "sl-violations" not exists
jsonpath "$.status" == "healthy"
"""
        test_file.write_text(test_content, encoding="utf-8")
        smooth_print(f"  {GREEN}✓ Test base de contrato creado:{NC} tests/000_health.hurl", 0.05)

    smooth_print(f"\n{GREEN}{BOLD}🎉 Proyecto inicializado con éxito bajo Spec-First.{NC}\n", 0.1)
