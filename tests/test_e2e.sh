#!/usr/bin/env sh
# End-to-end tests: every user-facing command, run for real through the shell
# wrappers. Unit tests exercise the core directly and the shell tests check the
# wiring; this checks that a person typing a command gets a working command.
#
#     bash tests/test_e2e.sh
#     zsh  tests/test_e2e.sh
#
# Read-only checks run against the caller's real profiles. Everything that
# writes runs in a throwaway HOME.
set -u

REPO=$(cd "$(dirname "$0")/.." && pwd)
if [ -n "${ZSH_VERSION:-}" ]; then SH=zsh; else SH=bash; fi
LAYER="$REPO/shell/claude-profiles.$SH"
PASS=0; FAIL=0

# a fresh non-interactive shell per case, with the layer sourced
_run() { $SH -c ". \"$LAYER\" >/dev/null 2>&1; $1" 2>&1; }

expect() {  # expect <desc> <command> <substring>
  out=$(_run "$2")
  case "$out" in
    *"$3"*) PASS=$((PASS+1)); printf '  ok    %s\n' "$1" ;;
    *) FAIL=$((FAIL+1)); printf "  FAIL  %s — expected '%s'\n" "$1" "$3"
       printf '%s\n' "$out" | head -3 | sed 's/^/          /' ;;
  esac
}
check() {   # check <desc> <shell test>
  if eval "$2"; then PASS=$((PASS+1)); printf '  ok    %s\n' "$1"
  else FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; fi
}

SANDBOX=$(mktemp -d 2>/dev/null || mktemp -d -t cpe2e)
export HOME="$SANDBOX"
export CLAUDE_PROFILE_HOME="$SANDBOX/.claude-profiles"
# do not inherit the developer's own settings - these tests assert on defaults
unset CLAUDE_CONFIG_DIR CLAUDE_PROFILE_NAME CLAUDE_DEFAULT_PROFILE \
      CLAUDE_PROFILE_PROMPT CLAUDE_PROFILE_SHOW_DEFAULT \
      CLAUDE_PROFILE_PROMPT_PREFIX 2>/dev/null || true
mkdir -p "$HOME/.claude" "$CLAUDE_PROFILE_HOME"

printf 'end to end (%s)\n' "$SH"

echo "-- switching --"
expect "claude-profile with no args"      'claude-profile'                                  "claude profile:"
expect "switching takes effect"           'claude-profile alpha; claude-profile'            "alpha"
expect "default clears the config dir"    'claude-profile alpha; claude-profile default; echo "[${CLAUDE_CONFIG_DIR:-unset}]"' "[unset]"
expect "a traversal name is refused"      'claude-profile ../escape 2>&1'                   "invalid profile name"
check  "creating a profile makes its dir" '$SH -c ". \"$LAYER\" >/dev/null 2>&1; claude-profile alpha" >/dev/null 2>&1; [ -d "$CLAUDE_PROFILE_HOME/alpha" ]'

echo "-- listing --"
expect "claude-profiles"                  'claude-profiles'                                 "PROFILE"
expect "  --plain"                        'claude-profiles --plain'                         "PROFILE"
expect "  --dirs"                         'claude-profiles --dirs'                          "CONFIG DIR"
expect "  --no-usage"                     'claude-profiles --no-usage'                      "AUTH"

echo "-- every core subcommand really runs --"
for sub in $("${CLAUDE_PY:-python3}" "$REPO/bin/claude-profiles.py" --help 2>&1 \
             | grep -oE '\{[a-z,]+\}' | head -1 | tr -d '{}' | tr ',' ' '); do
  case "$sub" in
    path)       expect "  path"       'claude-profiles path alpha'                 "alpha" ;;
    status)     expect "  status"     'claude-profiles status --plain'             "PROFILE" ;;
    doctor)     expect "  doctor"     'claude-profiles doctor'                     "environment" ;;
    update)     expect "  update"     'claude-profiles update --check 2>&1'        "installed:" ;;
    prune)      expect "  prune"      'claude-profiles prune -o 9999'              "nothing older" ;;
    best)       expect "  best"       'claude-profiles best --cached 2>&1'         "" ;;
    clone)      expect "  clone"      'claude-profiles clone alpha beta 2>&1'      "" ;;
    statusline) expect "  statusline" 'claude-profiles statusline --show profile </dev/null' "" ;;
    sessions)   expect "  sessions"   'claude-profiles sessions -a 2>&1'           "" ;;
    remove)     expect "  remove"     'claude-profiles remove nosuch --yes 2>&1'   "no such profile" ;;
    handoff)    expect "  handoff"    'claude-profiles handoff nosuch 2>&1'        "no such profile" ;;
    *)          expect "  $sub"       "claude-profiles $sub 2>&1"                  "" ;;
  esac
done

echo "-- clone --"
_run 'claude-profile alpha >/dev/null; printf "{\"t\":1}" > "$CLAUDE_PROFILE_HOME/alpha/settings.json"; printf SECRET > "$CLAUDE_PROFILE_HOME/alpha/.credentials.json"' >/dev/null
expect "copies settings"                  'claude-profile-clone alpha beta'                 "copied into"
check  "  settings.json arrived"          '[ -f "$CLAUDE_PROFILE_HOME/beta/settings.json" ]'
check  "  credentials never copied"       '[ ! -f "$CLAUDE_PROFILE_HOME/beta/.credentials.json" ]'
expect "refuses default as the target"    'claude-profile-clone alpha default 2>&1'         "refusing"
expect "leaves existing files alone"      'claude-profile-clone alpha beta 2>&1'            "already present"
expect "--force overwrites"               'claude-profile-clone alpha beta --force'         "copied into"

echo "-- handoff --"
_run 'mkdir -p "$HOME/.claude/projects/-tmp-proj"; printf "{\"type\":\"user\",\"cwd\":\"/tmp/proj\",\"message\":{\"content\":\"hello\"}}\n" > "$HOME/.claude/projects/-tmp-proj/aaa11111-0000-0000-0000-000000000000.jsonl"' >/dev/null
expect "copies a session"                 'claude-handoff alpha aaa11111 -d /tmp/proj'      "handed off"
check  "  landed in the target"           '[ -n "$(find "$CLAUDE_PROFILE_HOME/alpha/projects" -name "aaa11111*" 2>/dev/null)" ]'
check  "  original survives"              '[ -f "$HOME/.claude/projects/-tmp-proj/aaa11111-0000-0000-0000-000000000000.jsonl" ]'
expect "refuses an unknown target"        'claude-handoff nosuch -d /tmp/proj 2>&1'         "no such profile"
expect "refuses a traversal target"       'claude-handoff ../escape -d /tmp/proj 2>&1'      "invalid profile name"

echo "-- sessions --"
expect "lists them"                       'claude-sessions -a -d /tmp/proj'                 "SESSION ID"
expect "  --grep matches"                 'claude-sessions -a --grep hello'                 "SESSION ID"
expect "  --grep with no match"           'claude-sessions -a --grep zzzqqq 2>&1'           "no sessions"
expect "  invalid regex is reported"      'claude-sessions -a --grep "[bad" 2>&1'           "bad --grep"
expect "  --plain"                        'claude-sessions -a --plain'                      "WHEN"

echo "-- statusline --"
expect "renders"                          'claude-profile alpha; claude-profiles statusline --show profile </dev/null' "alpha"
expect "--install"                        'claude-profile alpha; claude-profiles statusline --install' "status line enabled"
check  "  written into settings.json"     'grep -q statusline "$CLAUDE_PROFILE_HOME/alpha/settings.json"'
expect "--install-all"                    'claude-profiles statusline --install-all'        "status line enabled"

echo "-- exec --"
expect "sets the dir for the child"       'claude-profile-exec alpha sh -c "printf %s \$CLAUDE_CONFIG_DIR"' "alpha"
expect "  leaves this shell alone"        'claude-profile-exec alpha true; echo "[${CLAUDE_PROFILE_NAME:-unset}]"' "[unset]"
expect "  refuses an unknown profile"     'claude-profile-exec nosuch true 2>&1'            "no such profile"
expect "  needs a command"                'claude-profile-exec alpha 2>&1'                  "usage:"

echo "-- prune --"
expect "dry run says so"                  'claude-prune -o 0 2>&1'                          "dry run"
check  "  deletes nothing"                '[ -n "$(find "$CLAUDE_PROFILE_HOME/alpha/projects" -name "aaa11111*" 2>/dev/null)" ]'
expect "--yes deletes"                    'claude-prune -o 0 --yes 2>&1'                    "deleted"
check  "  transcript is gone"             '[ -z "$(find "$CLAUDE_PROFILE_HOME/alpha/projects" -name "aaa11111*" 2>/dev/null)" ]'

echo "-- remove --"
expect "refuses default"                  'claude-profile-remove default --yes 2>&1'        "refusing"
expect "refuses a traversal name"         'claude-profile-remove ../escape --yes 2>&1'      "invalid profile name"
expect "removes a profile"                'claude-profile-remove beta --yes'                "removed profile"
check  "  its directory is gone"          '[ ! -d "$CLAUDE_PROFILE_HOME/beta" ]'
check  "  other profiles survive"         '[ -d "$CLAUDE_PROFILE_HOME/alpha" ]'
expect "resets the shell if it was active" 'claude-profile alpha; claude-profile-remove alpha --yes >/dev/null; echo "[${CLAUDE_PROFILE_NAME:-unset}]"' "[unset]"

echo "-- markers --"
_run 'mkdir -p "$HOME/p/repo/sub"; claude-profile gamma >/dev/null; echo gamma > "$HOME/p/.claude-profile"' >/dev/null
expect "a marker selects its profile"     'cd "$HOME/p/repo/sub"; _claude_profile_last_pwd=x; _claude_profile_auto; claude-profile' "gamma"
expect "elsewhere falls back to default"  'cd "$HOME"; _claude_profile_last_pwd=x; _claude_profile_auto; claude-profile' "default"
expect "CLAUDE_DEFAULT_PROFILE is used"   'export CLAUDE_DEFAULT_PROFILE=gamma; cd "$HOME"; _claude_profile_last_pwd=x; _claude_profile_auto; claude-profile' "gamma"

echo "-- prompt --"
expect "names a non-default profile"      'claude-profile gamma; claude_profile_prompt'     "gamma"
expect "stays quiet on default"           'claude-profile default; echo "[$(claude_profile_prompt)]"' "[]"
expect "quiet on a configured default"    'export CLAUDE_DEFAULT_PROFILE=gamma; claude-profile gamma; echo "[$(claude_profile_prompt)]"' "[]"
expect "speaks up away from it"           'export CLAUDE_DEFAULT_PROFILE=gamma; claude-profile alpha; claude_profile_prompt' "alpha"
expect "SHOW_DEFAULT overrides the silence" 'export CLAUDE_DEFAULT_PROFILE=gamma CLAUDE_PROFILE_SHOW_DEFAULT=1; claude-profile gamma; claude_profile_prompt' "gamma"

cd / || exit 1
rm -rf "$SANDBOX"
printf '\n%s: %d passed, %d failed\n' "$SH" "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
