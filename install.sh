#!/usr/bin/env sh
# Install Claude Code multi-account profiles (macOS / Linux / WSL / Git-Bash).
# Usage:  sh install.sh
set -e
SRC=$(cd "$(dirname "$0")" && pwd)
DEST="${CLAUDE_PROFILE_HOME:-$HOME/.claude-profiles}"

command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || {
  echo "error: python3 not found. Install it first (apt install python3 / brew install python)." >&2
  exit 1; }

if [ "$SRC" != "$DEST" ]; then
  mkdir -p "$DEST/bin" "$DEST/shell"
  cp "$SRC/bin/claude-profiles.py" "$DEST/bin/"
  cp "$SRC/shell/claude-profiles.zsh" "$SRC/shell/claude-profiles.bash" "$DEST/shell/"
  [ -f "$SRC/shell/ClaudeProfiles.psm1" ] && cp "$SRC/shell/ClaudeProfiles.psm1" "$DEST/shell/" || true
  [ -f "$SRC/README.md" ] && cp "$SRC/README.md" "$DEST/" || true
fi
chmod +x "$DEST/bin/claude-profiles.py"

add_line() {
  rc="$1"; line="$2"; marker="$3"
  [ -f "$rc" ] || touch "$rc"
  if grep -Fq "$marker" "$rc" 2>/dev/null; then
    echo "  already wired: $rc"
  else
    cp "$rc" "$rc.bak.$(date +%Y%m%d%H%M%S)"
    printf '\n# Claude Code multi-account profiles\n%s\n' "$line" >> "$rc"
    echo "  added to: $rc  (backup alongside)"
  fi
}

echo "installing to $DEST"
if [ -f "$HOME/.zshrc" ] || [ -n "$ZSH_VERSION" ]; then
  add_line "$HOME/.zshrc"  "source \"$DEST/shell/claude-profiles.zsh\"" "claude-profiles.zsh"
fi
if [ -f "$HOME/.bashrc" ] || [ -n "$BASH_VERSION" ]; then
  add_line "$HOME/.bashrc" "source \"$DEST/shell/claude-profiles.bash\"" "claude-profiles.bash"
fi

echo
echo "done. restart your shell (or: exec \$SHELL -l), then:"
echo "  claude-profiles                  list profiles"
echo "  claude-profile work && claude    log a 2nd account in via /login"
