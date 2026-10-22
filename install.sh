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

# Detección de arquitectura y SO
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ARCH_ALT="amd64" ;;
  aarch64|arm64) ARCH_ALT="arm64" ;;
  *) ARCH_ALT="amd64" ;;
esac

install_hurl() {
  echo "📦 Instalando binario oficial de Hurl en $BIN_DIR..."
  HURL_VERSION="8.0.1"
  TMP_DIR="$(mktemp -d)"
  if [ "$OS" = "linux" ]; then
    curl -fsSL "https://github.com/Orange-OpenSource/hurl/releases/download/${HURL_VERSION}/hurl-${HURL_VERSION}-${ARCH}-unknown-linux-gnu.tar.gz" | tar -xz -C "$TMP_DIR"
    cp "$TMP_DIR/hurl-${HURL_VERSION}-${ARCH}-unknown-linux-gnu/hurl" "$BIN_DIR/hurl"
    chmod +x "$BIN_DIR/hurl"
  fi
  rm -rf "$TMP_DIR"
  echo "  ✓ Hurl instalado correctamente."
}

install_gh() {
  echo "📦 Instalando binario oficial de GitHub CLI (gh) en $BIN_DIR..."
  GH_VERSION="2.103.0"
  TMP_DIR="$(mktemp -d)"
  curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${ARCH_ALT}.tar.gz" | tar -xz -C "$TMP_DIR"
  cp "$TMP_DIR/gh_${GH_VERSION}_linux_${ARCH_ALT}/bin/gh" "$BIN_DIR/gh"
  chmod +x "$BIN_DIR/gh"
  rm -rf "$TMP_DIR"
  echo "  ✓ gh instalado correctamente."
}

install_opencode() {
  echo "📦 Instalando OpenCode CLI en el sistema..."
  curl -fsSL https://opencode.ai/install | bash
  echo "  ✓ OpenCode instalado."
}

echo "Resolviendo dependencias profesionales:"

# 1. Hurl
if command -v hurl >/dev/null 2>&1 || [ -x "$BIN_DIR/hurl" ]; then
  echo "  ✓ Hurl detectado"
else
  install_hurl
fi

# 2. GitHub CLI (gh)
if command -v gh >/dev/null 2>&1 || [ -x "$BIN_DIR/gh" ]; then
  echo "  ✓ GitHub CLI (gh) detectado"
else
  install_gh
fi

# 3. OpenCode
if command -v opencode >/dev/null 2>&1 || [ -x "$BIN_DIR/opencode" ]; then
  echo "  ✓ OpenCode detectado"
else
  install_opencode
fi

# 4. Prism
if command -v prism >/dev/null 2>&1; then
  echo "  ✓ Prism CLI detectado"
else
  echo "  ✓ Prism se ejecutará vía npx oficial de Stoplight automáticamente."
fi
echo ""
echo "🚀 ¡Listo! Ejecutá 'chelo-harness' en cualquier repositorio Git para arrancar."
