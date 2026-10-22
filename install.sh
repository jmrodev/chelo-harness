#!/usr/bin/env bash
# install.sh — Instalador de chelo-harness para Linux y macOS
set -euo pipefail

echo "🛡️  Instalando Chelo-Harness..."

BIN_DIR="$HOME/.local/bin"
LIB_DIR="$HOME/.local/lib/chelo"

mkdir -p "$BIN_DIR" "$LIB_DIR"

BASE_URL="https://raw.githubusercontent.com/jmrodev/chelo-harness/main"

# Descargar ejecutable principal
curl -fsSL "$BASE_URL/bin/chelo-harness" -o "$BIN_DIR/chelo-harness"
chmod +x "$BIN_DIR/chelo-harness"

# Descargar librería de canales
curl -fsSL "$BASE_URL/lib/chelo_channels.py" -o "$LIB_DIR/chelo_channels.py"

echo "✓ Chelo-Harness instalado en $BIN_DIR/chelo-harness"
echo ""
echo "Verificando dependencias recomendadas:"
command -v prism >/dev/null 2>&1 && echo "  ✓ Prism CLI detectado" || echo "  ⚠️  Prism no encontrado (instalar con: npm install -g @stoplight/prism-cli)"
command -v hurl >/dev/null 2>&1 && echo "  ✓ Hurl detectado" || echo "  ⚠️  Hurl no encontrado (instalar desde https://hurl.dev o vía gestor de paquetes)"
command -v gh >/dev/null 2>&1 && echo "  ✓ GitHub CLI detectado" || echo "  ⚠️  gh no encontrado"
echo ""
echo "🚀 ¡Listo! Ejecutá 'chelo-harness' en cualquier repositorio Git para arrancar."
