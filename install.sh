#!/usr/bin/env bash
# install.sh — Instalador de chelo-harness para Linux y macOS
set -euo pipefail

echo "🛡️  Instalando Chelo-Harness..."

BIN_DIR="$HOME/.local/bin"
LIB_DIR="$HOME/.local/lib/chelo"
AGENTS_DIR="$HOME/.local/share/chelo/agents"

mkdir -p "$BIN_DIR" "$LIB_DIR" "$AGENTS_DIR"

TARBALL_URL="https://github.com/jmrodev/chelo-harness/archive/refs/heads/main.tar.gz"

# Un solo tarball en vez de una descarga por archivo: la lista hardcodeada se
# desincronizaba con cada módulo nuevo y no soporta paquetes (lib/ai/tools/,
# lib/mcp/handlers/). Con el árbol completo, agregar un archivo no toca el
# instalador.
SRC_DIR="$(mktemp -d)"
trap 'rm -rf "$SRC_DIR"' EXIT

curl -fsSL "$TARBALL_URL" | tar -xz -C "$SRC_DIR"
SRC_ROOT="$(find "$SRC_DIR" -maxdepth 1 -mindepth 1 -type d | head -n 1)"
if [ -z "$SRC_ROOT" ] || [ ! -d "$SRC_ROOT/lib" ]; then
  echo "✗ No se pudo descargar el árbol del repositorio desde $TARBALL_URL" >&2
  exit 1
fi

mkdir -p "$LIB_DIR/lib" "$AGENTS_DIR"
cp -R "$SRC_ROOT/lib/." "$LIB_DIR/lib/"
cp "$SRC_ROOT/bin/chelo-harness" "$BIN_DIR/chelo-harness"
chmod +x "$BIN_DIR/chelo-harness"
cp -R "$SRC_ROOT/agents/." "$AGENTS_DIR/" 2>/dev/null || true

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
  echo "📦 Instalando paquete oficial de Hurl..."
  HURL_VERSION="8.0.1"
  TMP_DIR="$(mktemp -d)"

  # Si estamos en Debian/Ubuntu y hay sudo/apt, usar apt con el .deb oficial
  if [ -f /etc/debian_version ] && command -v apt >/dev/null 2>&1; then
    DEB_URL="https://github.com/Orange-OpenSource/hurl/releases/download/${HURL_VERSION}/hurl_${HURL_VERSION}_${ARCH_ALT}.deb"
    if curl -fsSL -o "$TMP_DIR/hurl.deb" "$DEB_URL" 2>/dev/null; then
      if [ "$(id -u)" -eq 0 ]; then
        apt install -y "$TMP_DIR/hurl.deb"
      elif command -v sudo >/dev/null 2>&1; then
        sudo apt install -y "$TMP_DIR/hurl.deb"
      fi
    fi
  fi

  # Fallback a binario en ~/.local/bin si no se instaló a nivel sistema
  if ! command -v hurl >/dev/null 2>&1; then
    echo "   (Instalando binario estático en $BIN_DIR/hurl)"
    if [ "$OS" = "linux" ]; then
      curl -fsSL "https://github.com/Orange-OpenSource/hurl/releases/download/${HURL_VERSION}/hurl-${HURL_VERSION}-${ARCH}-unknown-linux-gnu.tar.gz" | tar -xz -C "$TMP_DIR"
      cp "$TMP_DIR/hurl-${HURL_VERSION}-${ARCH}-unknown-linux-gnu/bin/hurl" "$BIN_DIR/hurl"
      chmod +x "$BIN_DIR/hurl"
    fi
  fi

  rm -rf "$TMP_DIR"
  echo "  ✓ Hurl instalado correctamente."
}

install_prism() {
  echo "📦 Instalando binario oficial standalone de Prism en $BIN_DIR..."
  PRISM_URL="https://github.com/stoplightio/prism/releases/download/v5.12.0/prism-cli-linux"
  if [ "$OS" = "darwin" ]; then
    PRISM_URL="https://github.com/stoplightio/prism/releases/download/v5.12.0/prism-cli-macos"
  fi
  curl -fsSL "$PRISM_URL" -o "$BIN_DIR/prism"
  chmod +x "$BIN_DIR/prism"
  echo "  ✓ Prism standalone instalado correctamente (soporte 100% offline)."
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

# Si se pasa el flag --upgrade o no existen, instala/actualiza las binarias oficiales
UPGRADE_ALL=false
if [ "${1:-}" = "--upgrade" ] || [ "${1:-}" = "update" ]; then
  UPGRADE_ALL=true
fi

echo "Resolviendo y asegurando dependencias profesionales:"

# 1. Hurl
if [ "$UPGRADE_ALL" = true ] || (! command -v hurl >/dev/null 2>&1 && [ ! -x "$BIN_DIR/hurl" ]); then
  install_hurl
else
  echo "  ✓ Hurl detectado"
fi

# 2. GitHub CLI (gh)
if [ "$UPGRADE_ALL" = true ] || (! command -v gh >/dev/null 2>&1 && [ ! -x "$BIN_DIR/gh" ]); then
  install_gh
else
  echo "  ✓ GitHub CLI (gh) detectado"
fi

# 3. OpenCode
if [ -x "$HOME/.opencode/bin/opencode" ] || [ -x "$BIN_DIR/opencode" ] || command -v opencode >/dev/null 2>&1; then
  echo "  ✓ OpenCode detectado en disco (omitiendo descarga)"
elif [ "$UPGRADE_ALL" = true ] || ! command -v opencode >/dev/null 2>&1; then
  install_opencode
fi

# 4. Prism (Offline Standalone)
if [ "$UPGRADE_ALL" = true ] || (! command -v prism >/dev/null 2>&1 && [ ! -x "$BIN_DIR/prism" ]); then
  install_prism
else
  echo "  ✓ Prism CLI detectado"
fi

install_agy() {
  # Verificar si la CPU soporta la instrucción obligatoria pclmulqdq requerida por Antigravity
  if grep -m 1 flags /proc/cpuinfo 2>/dev/null | grep -q -w "pclmulqdq"; then
    echo "📦 Instalando Google Antigravity CLI (agy) oficial..."
    curl -fsSL https://antigravity.google/cli/install.sh | bash
    echo "  ✓ Antigravity CLI instalado."
  else
    echo "  ○ Antigravity CLI omitido (la CPU no cuenta con la instrucción de hardware pclmul requerida)."
  fi
}

# 5. Antigravity (AGY)
if ! command -v agy >/dev/null 2>&1 && [ ! -x "$BIN_DIR/agy" ]; then
  install_agy
else
  echo "  ✓ Antigravity CLI detectado"
fi
echo ""
echo "🚀 ¡Listo! Ejecutá 'chelo-harness' en cualquier repositorio Git para arrancar."
