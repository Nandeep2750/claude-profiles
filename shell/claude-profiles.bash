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

# Profile names become directory names, so reject anything that could escape
# CLAUDE_PROFILE_HOME. Mirrors check_name() in bin/claude-profiles.py.
_claude_valid_name() {
  [ "$1" = "default" ] && return 0
  case "$1" in
    *..*|"") ;;
    *) case "$1" in [A-Za-z0-9]*) 
         case "$1" in *[!A-Za-z0-9._-]*) ;; *) return 0 ;; esac ;;
       esac ;;
  esac
  echo "invalid profile name: $1" >&2
  echo "names may contain letters, digits, '.', '-' and '_', and must start with a letter or digit" >&2
  return 1
}

claude-profile() {
  case "$1" in
    "")      echo "claude profile: ${CLAUDE_PROFILE_NAME:-default}"
             echo "config dir    : ${CLAUDE_CONFIG_DIR:-$HOME/.claude}" ;;
    default) unset CLAUDE_CONFIG_DIR CLAUDE_PROFILE_NAME ;;
    *)       _claude_valid_name "$1" || return 1
             export CLAUDE_CONFIG_DIR="$CLAUDE_PROFILE_HOME/$1"
             export CLAUDE_PROFILE_NAME="$1"
             [ -d "$CLAUDE_CONFIG_DIR" ] || mkdir -p "$CLAUDE_CONFIG_DIR" ;;
  esac
}
# `claude-profiles` with no subcommand means `status`; anything else passes through.
claude-profiles() {
  case "$1" in
    status|sessions|handoff|remove|doctor|path|clone|prune|best|update) "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" "$@" ;;
    *)                                          "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" status "$@" ;;
  esac
}
claude-doctor()   { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" doctor "$@"; }
claude-profile-clone() { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" clone "$@"; }
claude-prune()    { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" prune "$@"; }
claude-best()     { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" best  "$@"; }
claude-update()   { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" update "$@"; }
claude-version()  { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" --version; }

# Launch claude on whichever signed-in account has the most headroom.
claude-auto() {
  local pick
  pick=$("$CLAUDE_PY" "$CLAUDE_PROFILE_PY" best --quiet) || return $?
  [ -n "$pick" ] || return 1
  printf 'using profile %s\n' "$pick" >&2
  claude-profile-exec "$pick" claude "$@"
}

# Run one command under a profile without switching this shell.
#   claude-profile-exec work claude -p "summarise this repo"
claude-profile-exec() {
  local name="$1"
  if [ -z "$name" ] || [ "$#" -lt 2 ]; then
    echo "usage: claude-profile-exec PROFILE COMMAND [ARGS...]" >&2; return 2
  fi
  shift
  if [ "$name" = default ]; then
    env -u CLAUDE_CONFIG_DIR -u CLAUDE_PROFILE_NAME "$@"
  else
    _claude_valid_name "$name" || return 1
    local dir="$CLAUDE_PROFILE_HOME/$name"
    [ -d "$dir" ] || { echo "no such profile: $name" >&2; return 1; }
    CLAUDE_CONFIG_DIR="$dir" CLAUDE_PROFILE_NAME="$name" "$@"
  fi
}
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
  claude-profile "${name:-${CLAUDE_DEFAULT_PROFILE:-default}}"
}
case "${PROMPT_COMMAND:-}" in
  *_claude_profile_auto*) ;;
  "") PROMPT_COMMAND="_claude_profile_auto" ;;
  *)  PROMPT_COMMAND="_claude_profile_auto;$PROMPT_COMMAND" ;;
esac

# Optional prompt indicator - set CLAUDE_PROFILE_PROMPT=1 before sourcing.
claude_profile_prompt() {
  local n="${CLAUDE_PROFILE_NAME:-${CLAUDE_DEFAULT_PROFILE:-default}}"
  if [ "$n" = "default" ] && [ -z "${CLAUDE_PROFILE_SHOW_DEFAULT:-}" ]; then return; fi
  printf '%s%s' "${CLAUDE_PROFILE_PROMPT_PREFIX:-claude:}" "$n"
}
if [ -n "${CLAUDE_PROFILE_PROMPT:-}" ]; then
  case "${PS1:-}" in
    *claude_profile_prompt*) ;;
    *) PS1='$(claude_profile_prompt) '"${PS1:-}" ;;
  esac
fi

_claude_profile_complete() {
  local names
  names="default $(ls -1 "$CLAUDE_PROFILE_HOME" 2>/dev/null | tr '\n' ' ')"
  mapfile -t COMPREPLY < <(compgen -W "$names" -- "${COMP_WORDS[COMP_CWORD]}")
}
complete -F _claude_profile_complete claude-profile
complete -F _claude_profile_complete claude-profile-remove
complete -F _claude_profile_complete claude-profile-exec
complete -F _claude_profile_complete claude-profile-clone
complete -F _claude_profile_complete claude-handoff
complete -W "-a --all -A --all-profiles -p --profile -n --limit -f --full -d --dir --plain -g --grep" claude-sessions
complete -W "-o --older-than -p --profile -n --limit -y --yes --plain" claude-prune
complete -W "-c --check" claude-update
complete -W "status doctor sessions handoff remove clone prune best update path --live --dirs --no-usage --plain" claude-profiles
