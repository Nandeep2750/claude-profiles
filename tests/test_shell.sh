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

for fn in claude-profile claude-profiles claude-sessions claude-handoff \
          claude-profile-remove claude-doctor claude-profile-exec \
          claude-profile-clone claude_profile_prompt claude-prune \
          claude-best claude-auto claude-update claude-version; do
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
mkdir -p "$HOME/projects/sample-project/api/src" "$HOME/projects/other"
echo work > "$HOME/projects/sample-project/.claude-profile"
mkdir -p "$CLAUDE_PROFILE_HOME/solo"
echo solo > "$HOME/projects/sample-project/api/.claude-profile"

cd "$HOME/projects/sample-project" || exit 1
_claude_profile_last_pwd=force; _claude_profile_auto
is "marker selects its profile" "work" "${CLAUDE_PROFILE_NAME:-}"

cd "$HOME/projects/sample-project/api/src" || exit 1
_claude_profile_last_pwd=force; _claude_profile_auto
is "nearest marker wins over an ancestor" "solo" "${CLAUDE_PROFILE_NAME:-}"

cd "$HOME/projects/other" || exit 1
_claude_profile_last_pwd=force; _claude_profile_auto
is "no marker falls back to default" "" "${CLAUDE_PROFILE_NAME:-}"

# CLAUDE_DEFAULT_PROFILE changes where unmarked directories land
mkdir -p "$CLAUDE_PROFILE_HOME/fallback"
export CLAUDE_DEFAULT_PROFILE=fallback   # read by the cd hook
cd "$HOME/projects/other" || exit 1
_claude_profile_last_pwd=force; _claude_profile_auto
is "CLAUDE_DEFAULT_PROFILE is used when no marker" "fallback" "${CLAUDE_PROFILE_NAME:-}"
unset CLAUDE_DEFAULT_PROFILE
claude-profile default >/dev/null

# a marker still wins over the configured default
export CLAUDE_DEFAULT_PROFILE=fallback   # read by the cd hook
cd "$HOME/projects/sample-project" || exit 1
_claude_profile_last_pwd=force; _claude_profile_auto
is "a marker beats CLAUDE_DEFAULT_PROFILE" "work" "${CLAUDE_PROFILE_NAME:-}"
unset CLAUDE_DEFAULT_PROFILE
claude-profile default >/dev/null

# exec runs under a profile without changing this shell
OUT=$(claude-profile-exec work sh -c 'printf %s "$CLAUDE_CONFIG_DIR"')
is "exec sets CLAUDE_CONFIG_DIR for the child" "$CLAUDE_PROFILE_HOME/work" "$OUT"
is "exec leaves this shell alone" "" "${CLAUDE_PROFILE_NAME:-}"
claude-profile-exec nosuchprofile true >/dev/null 2>&1 \
  && bad "exec rejects unknown profiles" "non-zero" "zero" || ok "exec rejects unknown profiles"
claude-profile-exec work >/dev/null 2>&1 \
  && bad "exec needs a command" "non-zero" "zero" || ok "exec needs a command"

# prompt indicator
claude-profile work >/dev/null
has "prompt indicator names the profile" "$(claude_profile_prompt)" "work"
claude-profile default >/dev/null
is "prompt indicator is silent on default" "" "$(claude_profile_prompt)"

# clone copies settings but never credentials
printf '{"x":1}' > "$CLAUDE_PROFILE_HOME/work/settings.json"
printf 'secret'  > "$CLAUDE_PROFILE_HOME/work/.credentials.json"
mkdir -p "$CLAUDE_PROFILE_HOME/fresh"
claude-profile-clone work fresh >/dev/null 2>&1
[ -f "$CLAUDE_PROFILE_HOME/fresh/settings.json" ] && ok "clone copies settings.json" \
  || bad "clone copies settings.json" "copied" "missing"
[ -f "$CLAUDE_PROFILE_HOME/fresh/.credentials.json" ] \
  && bad "clone never copies credentials" "absent" "PRESENT" \
  || ok "clone never copies credentials"

# profile names must not be able to escape CLAUDE_PROFILE_HOME
mkdir -p "$HOME/outside"
claude-profile ../outside >/dev/null 2>&1
is "traversal name is refused by claude-profile" "" "${CLAUDE_CONFIG_DIR:-}"
claude-profile-exec ../outside true >/dev/null 2>&1 \
  && bad "traversal name is refused by exec" "non-zero" "zero" \
  || ok "traversal name is refused by exec"
claude-profile "a/b" >/dev/null 2>&1
is "slash in a name is refused" "" "${CLAUDE_CONFIG_DIR:-}"
claude-profile work >/dev/null
is "ordinary names still work" "work" "${CLAUDE_PROFILE_NAME:-}"
claude-profile default >/dev/null

# new subcommands dispatch through claude-profiles
for sub in prune best clone update; do
  claude-profiles "$sub" --help >/dev/null 2>&1 \
    && ok "claude-profiles $sub dispatches" \
    || bad "claude-profiles $sub dispatches" "exit 0" "non-zero"
done

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
