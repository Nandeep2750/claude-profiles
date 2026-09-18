# Claude Code multi-account profiles - bash (Ubuntu/WSL/Git-Bash)
# Source this from ~/.bashrc:  source ~/.claude-tools/shell/claude-profiles.bash
#
# CLAUDE_TOOLS_DIR  = this repo (logic, safe to commit)
# CLAUDE_PROFILE_HOME = account data (credentials, transcripts - never commit)
CLAUDE_TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: ${CLAUDE_PROFILE_HOME:="${HOME}/.claude-profiles"}
export CLAUDE_PROFILE_HOME
: ${CLAUDE_PROFILE_PY:="${CLAUDE_TOOLS_DIR}/bin/claude-profiles.py"}
: ${CLAUDE_PY:=$(command -v python3 || command -v python)}

claude-profile() {
  case "$1" in
    "")      echo "claude profile: ${CLAUDE_PROFILE_NAME:-default}"
             echo "config dir    : ${CLAUDE_CONFIG_DIR:-$HOME/.claude}" ;;
    default) unset CLAUDE_CONFIG_DIR CLAUDE_PROFILE_NAME ;;
    *)       export CLAUDE_CONFIG_DIR="$CLAUDE_PROFILE_HOME/$1"
             export CLAUDE_PROFILE_NAME="$1"
             [ -d "$CLAUDE_CONFIG_DIR" ] || mkdir -p "$CLAUDE_CONFIG_DIR" ;;
  esac
}
# `claude-profiles` with no subcommand means `status`; anything else passes through.
claude-profiles() {
  case "$1" in
    status|sessions|handoff|remove|doctor|path) "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" "$@" ;;
    *)                                          "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" status "$@" ;;
  esac
}
claude-doctor()   { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" doctor "$@"; }
claude-sessions() { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" sessions "$@"; }
claude-handoff()  { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" handoff  "$@"; }

# Delete a profile. Resets this shell to `default` if it removed the active one.
claude-profile-remove() {
  local name="$1"
  "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" remove "$@" || return $?
  [ "$name" = "${CLAUDE_PROFILE_NAME:-default}" ] && claude-profile default
  _claude_profile_last_pwd="__unset__"
  return 0
}

_claude_profile_last_pwd="__unset__"
_claude_profile_auto() {
  [ "$PWD" = "$_claude_profile_last_pwd" ] && return
  _claude_profile_last_pwd="$PWD"
  local dir="$PWD" name=""
  while [ -n "$dir" ] && [ "$dir" != "/" ]; do
    if [ -f "$dir/.claude-profile" ]; then
      name=$(head -1 "$dir/.claude-profile" | tr -d '[:space:]'); break
    fi
    dir=$(dirname "$dir")
  done
  claude-profile "${name:-default}"
}
case "${PROMPT_COMMAND:-}" in
  *_claude_profile_auto*) ;;
  "") PROMPT_COMMAND="_claude_profile_auto" ;;
  *)  PROMPT_COMMAND="_claude_profile_auto;$PROMPT_COMMAND" ;;
esac

_claude_profile_complete() {
  local names
  names="default $(ls -1 "$CLAUDE_PROFILE_HOME" 2>/dev/null | tr '\n' ' ')"
  COMPREPLY=( $(compgen -W "$names" -- "${COMP_WORDS[COMP_CWORD]}") )
}
complete -F _claude_profile_complete claude-profile
complete -F _claude_profile_complete claude-profile-remove
complete -F _claude_profile_complete claude-handoff
complete -W "-a --all -A --all-profiles -p --profile -n --limit -f --full -d --dir --plain" claude-sessions
complete -W "status doctor sessions handoff remove path --live --dirs --no-usage --plain" claude-profiles
