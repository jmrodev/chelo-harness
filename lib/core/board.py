#!/usr/bin/env python3
"""
Módulo de integración con Daily Board (Project Hub).

Inyecta el workflow de GitHub Pages que despliega el tablero del repositorio,
configura Pages cuando `gh` está autenticado y resuelve la URL pública.

Toda la lógica devuelve datos; la presentación queda en `cmd_board_*` y en el MCP.
"""

import re
import shutil
import subprocess
import webbrowser
from pathlib import Path

from lib.core.gate import check_git_repo
from lib.ui.console import BLUE, BOLD, CYAN, GREEN, NC, RED, YELLOW, banner, smooth_print

WORKFLOW_RELATIVE = Path(".github/workflows/board.yml")

BOARD_WORKFLOW = """# Powered by Daily Board — Creado por Juan Marcelo Rodríguez (@jmrodev)
name: Deploy Project Board

on:
  push:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  deploy-board:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Daily Board
        uses: actions/checkout@v4
        with:
          repository: jmrodev/daily-board
          ref: gh-pages
          path: ./board-site

      - name: Setup GitHub Pages
        uses: actions/configure-pages@v5

      - name: Upload Pages Artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: ./board-site

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
"""


def repo_root():
    result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip())


def repo_slug():
    """Devuelve 'owner/repo' a partir del remoto origin de GitHub."""
    result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
    if result.returncode != 0:
        return None
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", result.stdout.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def board_url(slug=None):
    slug = slug or repo_slug()
    if not slug or "/" not in slug:
        return None
    owner, repo = slug.split("/", 1)
    return f"https://{owner}.github.io/{repo}/"


def gh_authenticated():
    if not shutil.which("gh"):
        return False
    return subprocess.run(["gh", "auth", "status"], capture_output=True, text=True).returncode == 0


def configure_pages(slug):
    """Habilita GitHub Pages en modo GitHub Actions. Devuelve (ok, detalle)."""
    if not slug:
        return False, "Sin remoto origin de GitHub."
    if not gh_authenticated():
        return False, "gh no está instalado o no tiene sesión."

    created = subprocess.run(
        ["gh", "api", "-X", "POST", f"repos/{slug}/pages", "-f", "build_type=workflow"],
        capture_output=True,
        text=True,
    )
    if created.returncode == 0:
        return True, "GitHub Pages habilitado en modo GitHub Actions."

    updated = subprocess.run(
        ["gh", "api", "-X", "PUT", f"repos/{slug}/pages", "-f", "build_type=workflow"],
        capture_output=True,
        text=True,
    )
    if updated.returncode == 0:
        return True, "GitHub Pages actualizado a modo GitHub Actions."

    return False, (created.stderr or updated.stderr or "").strip() or "No se pudo configurar Pages."


def board_init(force=False):
    """Inyecta el workflow del tablero. Devuelve datos, sin imprimir."""
    root = repo_root()
    if not root:
        return {"ok": False, "error": "No estás dentro de un repositorio Git."}

    workflow = root / WORKFLOW_RELATIVE
    created = False
    if workflow.exists() and not force:
        pass
    else:
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(BOARD_WORKFLOW, encoding="utf-8")
        created = True

    slug = repo_slug()
    pages_ok, pages_detail = configure_pages(slug)

    return {
        "ok": True,
        "workflow": str(workflow),
        "created": created,
        "slug": slug,
        "pages_configured": pages_ok,
        "pages_detail": pages_detail,
        "url": board_url(slug),
        "manual_steps": not pages_ok,
        "next": "Commit y push del workflow para que Actions despliegue el tablero.",
    }


def cmd_board_init(force=False):
    banner()
    check_git_repo()
    result = board_init(force=force)
    if not result["ok"]:
        print(f"{RED}❌ {result['error']}{NC}")
        return result

    status = "ya existía" if not result["created"] else "creado"
    print(f"{GREEN}✓ Workflow {status}:{NC} {CYAN}{result['workflow']}{NC}")

    if result["pages_configured"]:
        print(f"{GREEN}✓ {result['pages_detail']}{NC}")
    else:
        print(f"{YELLOW}ℹ️  Pages no se configuró automáticamente:{NC} {result['pages_detail']}")
        if result["slug"]:
            print(f"   Abrí {CYAN}https://github.com/{result['slug']}/settings/pages{NC}")
            print(f"   y elegí {BOLD}Source → GitHub Actions{NC}.")

    if result["url"]:
        print(f"\n{BOLD}Tablero:{NC} {GREEN}{result['url']}{NC}")
    print(f"{YELLOW}⚠️  {result['next']}{NC}\n")
    return result


def cmd_board_open():
    banner()
    slug = repo_slug()
    url = board_url(slug)
    if not url:
        print(f"{RED}❌ No pude resolver el remoto origin de GitHub.{NC}")
        return None

    print(f"{BLUE}🌐 Abriendo el tablero del proyecto...{NC}")
    print(f"   {GREEN}{url}{NC}\n")
    try:
        webbrowser.open(url)
    except Exception:
        print(f"{YELLOW}No pude abrir el navegador. Entrá manualmente al enlace de arriba.{NC}")
    return url
