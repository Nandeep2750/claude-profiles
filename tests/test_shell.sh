#!/usr/bin/env sh
# Shell-layer tests. Run under either shell:
#     bash tests/test_shell.sh
#     zsh  tests/test_shell.sh
# Everything happens inside a throwaway HOME.
set -u

REPO=$(cd "$(dirname "$0")/.." && pwd)
PASS=0; FAIL=0

if [ -n "${ZSH_VERSION:-}" ]; then LAYER="$REPO/shell/claude-profiles.zsh"; SH_NAME=zsh
else                               LAYER="$REPO/shell/claude-profiles.bash"; SH_NAME=bash; fi

ok()   { PASS=$((PASS+1)); printf '  ok   %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL %s\n     expected: %s\n     actual  : %s\n' "$1" "$2" "$3"; }
is()   { [ "$2" = "$3" ] && ok "$1" || bad "$1" "$2" "$3"; }
has()  { case "$2" in *"$3"*) ok "$1" ;; *) bad "$1" "contains '$3'" "$2" ;; esac; }

TMP=$(mktemp -d 2>/dev/null || mktemp -d -t cp)
export HOME="$TMP"
export CLAUDE_PROFILE_HOME="$TMP/.claude-profiles"
mkdir -p "$HOME/.claude" "$CLAUDE_PROFILE_HOME"
unset CLAUDE_CONFIG_DIR CLAUDE_PROFILE_NAME 2>/dev/null || true

printf 'shell layer (%s)\n' "$SH_NAME"
# shellcheck disable=SC1090
. "$LAYER"

for fn in claude-profile claude-profiles claude-sessions claude-handoff claude-profile-remove claude-doctor; do
  if command -v "$fn" >/dev/null 2>&1; then ok "$fn is defined"; else bad "$fn is defined" "defined" "missing"; fi
done

claude-profile work >/dev/null
is "switching sets CLAUDE_PROFILE_NAME"  "work" "${CLAUDE_PROFILE_NAME:-}"
is "switching sets CLAUDE_CONFIG_DIR"    "$CLAUDE_PROFILE_HOME/work" "${CLAUDE_CONFIG_DIR:-}"
[ -d "$CLAUDE_PROFILE_HOME/work" ] && ok "switching creates the directory" \
  || bad "switching creates the directory" "exists" "missing"

claude-profile default >/dev/null
is "default clears CLAUDE_PROFILE_NAME" "" "${CLAUDE_PROFILE_NAME:-}"
is "default clears CLAUDE_CONFIG_DIR"   "" "${CLAUDE_CONFIG_DIR:-}"

# marker walk-up
mkdir -p "$HOME/projects/acme/api/src" "$HOME/projects/other"
echo work > "$HOME/projects/acme/.claude-profile"
mkdir -p "$CLAUDE_PROFILE_HOME/solo"
echo solo > "$HOME/projects/acme/api/.claude-profile"

cd "$HOME/projects/acme" || exit 1
_claude_profile_last_pwd=force; _claude_profile_auto
is "marker selects its profile" "work" "${CLAUDE_PROFILE_NAME:-}"

cd "$HOME/projects/acme/api/src" || exit 1
_claude_profile_last_pwd=force; _claude_profile_auto
is "nearest marker wins over an ancestor" "solo" "${CLAUDE_PROFILE_NAME:-}"

cd "$HOME/projects/other" || exit 1
_claude_profile_last_pwd=force; _claude_profile_auto
is "no marker falls back to default" "" "${CLAUDE_PROFILE_NAME:-}"

# the core is reachable through the wrappers
OUT=$(claude-profiles --plain --no-usage 2>&1)
has "claude-profiles prints a table" "$OUT" "PROFILE"
has "claude-profiles lists a profile" "$OUT" "work"

OUT=$(claude-profiles doctor 2>&1 || true)
has "claude-profiles doctor dispatches" "$OUT" "environment"
OUT=$(claude-doctor 2>&1 || true)
has "claude-doctor works" "$OUT" "profiles"

# removing the active profile resets the shell
claude-profile solo >/dev/null
claude-profile-remove solo --yes >/dev/null 2>&1
is "removing the active profile resets to default" "" "${CLAUDE_PROFILE_NAME:-}"
[ -d "$CLAUDE_PROFILE_HOME/solo" ] && bad "removed directory is gone" "missing" "still there" \
  || ok "removed directory is gone"

cd / || exit 1
rm -rf "$TMP"
printf '\n%s: %d passed, %d failed\n' "$SH_NAME" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
