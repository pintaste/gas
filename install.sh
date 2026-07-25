#!/usr/bin/env bash
# Install gas (Grok Account Switch) into ~/.local/bin (or PREFIX/bin)
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
REPO_RAW="${GAS_RAW_BASE:-https://raw.githubusercontent.com/pintaste/gas/main}"

mkdir -p "$BIN_DIR"

if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
  SRC_DIR=""
fi

if [[ -n "$SRC_DIR" && -f "$SRC_DIR/gas" ]]; then
  install -m 755 "$SRC_DIR/gas" "$BIN_DIR/gas"
  echo "✓ installed from local tree → $BIN_DIR/gas"
else
  TMP="$(mktemp)"
  trap 'rm -f "$TMP"' EXIT
  echo "↓ downloading gas from $REPO_RAW/gas"
  curl -fsSL "$REPO_RAW/gas" -o "$TMP"
  if ! head -1 "$TMP" | grep -q 'python'; then
    echo "error: downloaded file does not look like gas" >&2
    exit 1
  fi
  install -m 755 "$TMP" "$BIN_DIR/gas"
  echo "✓ installed from GitHub → $BIN_DIR/gas"
fi

# Remove old name if present (conflicted with git alias gss='git status -s')
if [[ -f "$BIN_DIR/gss" ]]; then
  # only remove if it looks like our tool
  if head -3 "$BIN_DIR/gss" 2>/dev/null | grep -q 'Grok account Switch\|Grok Account Switch'; then
    rm -f "$BIN_DIR/gss"
    echo "✓ removed old ~/.local/bin/gss (clashes with git alias gss)"
  fi
fi

if ! command -v gas >/dev/null 2>&1; then
  echo
  echo "Add to your shell PATH if needed:"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi

echo
echo "Note: the CLI is named 'gas' (not gss) because many shells alias"
echo "      gss → git status -s (oh-my-zsh / kaku)."
echo
echo "Quick start:"
echo "  gas add                # capture current login"
echo "  gas ls                 # list accounts + usage"
echo "  gas sw / gas to 2      # rotate or jump"
echo "  gas usage / refresh    # credits detail / token keepalive"
echo "  gas check / status     # diagnostics"
