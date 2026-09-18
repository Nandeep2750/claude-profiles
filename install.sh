#!/usr/bin/env sh
# Install Claude Code multi-account profiles (macOS / Linux / WSL / Git-Bash).
#
# Two directories, deliberately separate:
#   TOOLS  = this repo        -> logic only, safe to commit
#   DATA   = CLAUDE_PROFILE_HOME (default ~/.claude-profiles)
#            -> credentials, transcripts, per-account config. Never committed,
#               never synced. Run /login once per profile on each machine.
#
# Usage:  sh install.sh          (installs in place - run it from the clone)
set -e
TOOLS=$(cd "$(dirname "$0")" && pwd)
DATA="${CLAUDE_PROFILE_HOME:-$HOME/.claude-profiles}"

command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1 || {
  echo "error: python3 not found (apt install python3 / brew install python)." >&2; exit 1; }
command -v claude >/dev/null 2>&1 || \
  echo "warning: 'claude' not on PATH - install Claude Code before using this." >&2

mkdir -p "$DATA"
chmod +x "$TOOLS/bin/claude-profiles.py" 2>/dev/null || true

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

echo "tools (this repo): $TOOLS"
echo "account data     : $DATA"
if [ -f "$HOME/.zshrc" ] || [ -n "$ZSH_VERSION" ]; then
  add_line "$HOME/.zshrc"  "source \"$TOOLS/shell/claude-profiles.zsh\""  "claude-profiles.zsh"
fi
if [ -f "$HOME/.bashrc" ] || [ -n "$BASH_VERSION" ]; then
  add_line "$HOME/.bashrc" "source \"$TOOLS/shell/claude-profiles.bash\"" "claude-profiles.bash"
fi

echo
echo "done. restart your shell, then:"
echo "  claude-profiles                  list profiles"
echo "  claude-profile work && claude    add an account via /login"
