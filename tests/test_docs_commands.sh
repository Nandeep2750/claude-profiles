#!/usr/bin/env sh
# Run every command the documentation promises, in a throwaway HOME.
#
#     bash tests/test_docs_commands.sh
#     zsh  tests/test_docs_commands.sh
#
# Docs that show a command which does not work are worse than no docs. This
# extracts each one from the markdown and runs it, so the two cannot drift.
set -u

REPO=$(cd "$(dirname "$0")/.." && pwd)
if [ -n "${ZSH_VERSION:-}" ]; then SH=zsh; else SH=bash; fi
PASS=0; FAIL=0; SKIP=0

LIST=$(mktemp); trap 'rm -f "$LIST"' EXIT
"${CLAUDE_PY:-python3}" - "$REPO" > "$LIST" <<'PY'
import glob, os, re, sys
repo = sys.argv[1]
seen = set()
for f in sorted(glob.glob(f"{repo}/docs/**/*.md", recursive=True)) + [f"{repo}/README.md"]:
    with open(f) as fh:
        text = fh.read()
    for block in re.findall(r'```(?:sh|bash|console|zsh)\n(.*?)```', text, re.S):
        for line in block.splitlines():
            line = re.sub(r'\s*#.*$', '', line.strip().lstrip('$ ').strip())
            if line.startswith(('claude-', 'CLAUDE_CONFIG_DIR=')) and line not in seen:
                seen.add(line)
                print(line)
PY

T=$(mktemp -d 2>/dev/null || mktemp -d -t docsc)
export HOME="$T"; export CLAUDE_PROFILE_HOME="$T/.claude-profiles"
# do not inherit the developer's own settings
unset CLAUDE_CONFIG_DIR CLAUDE_PROFILE_NAME CLAUDE_DEFAULT_PROFILE \
      CLAUDE_PROFILE_PROMPT CLAUDE_PROFILE_SHOW_DEFAULT 2>/dev/null || true
mkdir -p "$HOME/.claude/projects/-p" "$CLAUDE_PROFILE_HOME" "$HOME/projects/p/api"
printf '{"oauthAccount":{"emailAddress":"you@example.com"}}' > "$HOME/.claude.json"
printf '{}' > "$HOME/.claude/.credentials.json"
printf '{"type":"user","cwd":"%s/projects/p/api","message":{"content":"rate limit"}}\n' "$HOME" \
  > "$HOME/.claude/projects/-p/0a9014e8-1111-2222-3333-444455556666.jsonl"
printf '{"type":"user","cwd":"%s/projects/p/api","message":{"content":"other"}}\n' "$HOME" \
  > "$HOME/.claude/projects/-p/2c24a68b-1111-2222-3333-444455556666.jsonl"

# shellcheck disable=SC1090
. "$REPO/shell/claude-profiles.$SH"
for p in work client; do claude-profile "$p" >/dev/null 2>&1; done
claude-profile default >/dev/null 2>&1
cd "$HOME/projects/p/api" || exit 1

printf 'documented commands (%s)\n' "$SH"
while IFS= read -r cmd; do
  [ -n "$cmd" ] || continue
  case "$cmd" in
    *"<"*|*"claude -p"*|*"claude mcp"*|*claude-auto*|*--yes*|*claude-update*|*claude-profile-remove*)
      SKIP=$((SKIP+1)); continue ;;
  esac
  out=$(eval "$cmd" 2>&1); rc=$?
  # these exit non-zero for legitimate reasons in a sandbox
  if [ $rc -eq 0 ] \
     || printf '%s' "$out" | grep -qE "no sessions|no match|same profile|nothing older|not logged in"; then
    PASS=$((PASS+1))
  else
    FAIL=$((FAIL+1)); printf '  FAIL  %s  (exit %s)\n' "$cmd" "$rc"
    printf '%s\n' "$out" | head -2 | sed 's/^/          /'
  fi
done < "$LIST"

# the functions must also survive a shell running in strict mode
printf '  -- strict mode --\n'
# claude-doctor is excluded on purpose: a throwaway HOME has no rc wiring, so
# it correctly reports a problem and exits 1. That is the check working.
for c in "claude-profile" "claude-profiles --no-usage" "claude-best --cached" \
         "claude-sessions -a" "claude_profile_prompt"; do
  if $SH -c "set -u 2>/dev/null || setopt nounset
             . \"$REPO/shell/claude-profiles.$SH\" >/dev/null 2>&1
             $c" >/dev/null 2>&1 || [ $? -eq 1 ]; then
    PASS=$((PASS+1)); printf '  ok    %s\n' "$c"
  else
    FAIL=$((FAIL+1)); printf '  FAIL  %s breaks under set -u\n' "$c"
  fi
done

cd /; rm -rf "$T"
printf '\n%s: %d ok, %d failed, %d skipped\n' "$SH" "$PASS" "$FAIL" "$SKIP"
[ "$FAIL" -eq 0 ]
