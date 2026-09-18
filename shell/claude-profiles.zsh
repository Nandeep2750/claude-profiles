# Claude Code multi-account profiles - zsh
# Source this from ~/.zshrc:  source ~/.claude-tools/shell/claude-profiles.zsh
#
# CLAUDE_TOOLS_DIR  = this repo (logic, safe to commit)
# CLAUDE_PROFILE_HOME = account data (credentials, transcripts - never commit)
CLAUDE_TOOLS_DIR="${${(%):-%x}:A:h:h}"          # derived from this file's location
: ${CLAUDE_PROFILE_HOME:="${HOME}/.claude-profiles"}
export CLAUDE_PROFILE_HOME
: ${CLAUDE_PROFILE_PY:="${CLAUDE_TOOLS_DIR}/bin/claude-profiles.py"}
: ${CLAUDE_PY:=$(command -v python3 || command -v python)}

claude-profile() {
  case "$1" in
    "")        print -r -- "claude profile: ${CLAUDE_PROFILE_NAME:-default}"
               print -r -- "config dir    : ${CLAUDE_CONFIG_DIR:-$HOME/.claude}" ;;
    default)   unset CLAUDE_CONFIG_DIR CLAUDE_PROFILE_NAME ;;
    *)         export CLAUDE_CONFIG_DIR="$CLAUDE_PROFILE_HOME/$1"
               export CLAUDE_PROFILE_NAME="$1"
               [[ -d "$CLAUDE_CONFIG_DIR" ]] || mkdir -p "$CLAUDE_CONFIG_DIR" ;;
  esac
}
# `claude-profiles` with no subcommand means `status`; anything else passes through.
claude-profiles() {
  case "$1" in
    status|sessions|handoff|remove|doctor|path) "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" "$@" ;;
    *)                                          "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" status "$@" ;;
  esac
}
claude-doctor()   { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" doctor "$@" }
claude-profile-clone() { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" clone "$@" }

# Run one command under a profile without switching this shell.
#   claude-profile-exec work claude -p "summarise this repo"
claude-profile-exec() {
  local name="$1"
  if [[ -z "$name" || $# -lt 2 ]]; then
    print -u2 "usage: claude-profile-exec PROFILE COMMAND [ARGS...]"; return 2
  fi
  shift
  if [[ "$name" == default ]]; then
    env -u CLAUDE_CONFIG_DIR -u CLAUDE_PROFILE_NAME "$@"
  else
    local dir="$CLAUDE_PROFILE_HOME/$name"
    [[ -d "$dir" ]] || { print -u2 "no such profile: $name"; return 1 }
    CLAUDE_CONFIG_DIR="$dir" CLAUDE_PROFILE_NAME="$name" "$@"
  fi
}
claude-sessions() { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" sessions "$@" }
claude-handoff()  { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" handoff  "$@" }

# Delete a profile. Resets this shell to `default` if it removed the active one.
claude-profile-remove() {
  local name="$1"
  "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" remove "$@" || return $?
  [[ "$name" == "${CLAUDE_PROFILE_NAME:-default}" ]] && claude-profile default
  _claude_profile_last_pwd="__unset__"   # let the cd hook re-resolve
  return 0
}

# auto-switch on cd: nearest .claude-profile file walking up from $PWD
_claude_profile_last_pwd="__unset__"
_claude_profile_auto() {
  [[ "$PWD" == "$_claude_profile_last_pwd" ]] && return
  _claude_profile_last_pwd="$PWD"
  local dir="$PWD" name=""
  while [[ -n "$dir" && "$dir" != "/" ]]; do
    if [[ -f "$dir/.claude-profile" ]]; then
      name=$(head -1 "$dir/.claude-profile" | tr -d '[:space:]'); break
    fi
    dir="${dir:h}"
  done
  claude-profile "${name:-${CLAUDE_DEFAULT_PROFILE:-default}}"
}
autoload -Uz add-zsh-hook
add-zsh-hook chpwd  _claude_profile_auto
add-zsh-hook precmd _claude_profile_auto

# Optional prompt indicator. Set CLAUDE_PROFILE_PROMPT=1 before sourcing this
# file to append the active profile to RPROMPT. claude_profile_prompt is also
# usable on its own if you build your prompt by hand.
claude_profile_prompt() {
  local n="${CLAUDE_PROFILE_NAME:-${CLAUDE_DEFAULT_PROFILE:-default}}"
  [[ "$n" == "default" && -z "${CLAUDE_PROFILE_SHOW_DEFAULT:-}" ]] && return
  print -rn -- "${CLAUDE_PROFILE_PROMPT_PREFIX:-claude:}$n"
}
if [[ -n "${CLAUDE_PROFILE_PROMPT:-}" ]]; then
  setopt prompt_subst
  case "$RPROMPT" in
    *claude_profile_prompt*) ;;
    *) RPROMPT='%F{242}$(claude_profile_prompt)%f'"${RPROMPT:-}" ;;
  esac
fi

# completion
if ! whence compdef >/dev/null 2>&1; then
  autoload -Uz compinit
  compinit -d "${XDG_CACHE_HOME:-$HOME/.cache}/zcompdump-$ZSH_VERSION" 2>/dev/null
fi
if whence compdef >/dev/null 2>&1; then
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'
zstyle ':completion:*:descriptions' format '%F{yellow}%d%f'

_claude_profile_names() {
  local -a names
  names=( default ${(f)"$(ls -1 "$CLAUDE_PROFILE_HOME" 2>/dev/null)"} )
  _describe -t profiles 'claude profile' names
}
compdef _claude_profile_names claude-profile

_claude_handoff() {
  case $CURRENT in
    2) _claude_profile_names ;;
    3) local -a ids
       ids=( ${(f)"$("$CLAUDE_PY" "$CLAUDE_PROFILE_PY" sessions -a -n 40 2>/dev/null | awk '{print $3}' | grep -E '^[0-9a-f-]{36}$')"} )
       _describe -t sessions 'session id' ids ;;
  esac
}
compdef _claude_handoff claude-handoff

_claude_sessions() {
  _arguments \
    '(-a --all)'{-a,--all}'[every directory, not just $PWD]' \
    '(-A --all-profiles)'{-A,--all-profiles}'[scan every profile]' \
    '(-p --profile)'{-p,--profile}'[profile to list]:profile:_claude_profile_names' \
    '(-n --limit)'{-n,--limit}'[max rows; bare flag = no limit]::count:' \
    '(-f --full)'{-f,--full}'[wrap long summaries instead of truncating]' \
    '(-d --dir)'{-d,--dir}'[directory to filter on]:dir:_files -/'
}
compdef _claude_sessions claude-sessions

_claude_profiles() {
  if (( CURRENT == 2 )) && [[ "$words[2]" != -* ]]; then
    local -a subs
    subs=(status:'profiles, accounts and usage' doctor:'check the install for problems'
          sessions:'list conversations' handoff:'copy a session to another profile'
          remove:'delete a profile' path:'print a profile config dir')
    _describe -t commands 'subcommand' subs && return
  fi
  _arguments \
    '--live[fetch current usage from the API instead of the cache]' \
    '--dirs[show each profile'"'"'s config dir]' \
    '--no-usage[hide the usage columns]' \
    '--plain[no borders - easier to pipe]'
}
compdef _claude_profiles claude-profiles

_claude_profile_remove() {
  _arguments '1:profile:_claude_profile_names' '(-y --yes)'{-y,--yes}'[skip confirmation]'
}
compdef _claude_profile_remove claude-profile-remove
compdef _claude_profile_names claude-profile-exec
_claude_profile_clone() { _arguments '1:source:_claude_profile_names' '2:target:_claude_profile_names' '(-f --force)'{-f,--force}'[overwrite]' }
compdef _claude_profile_clone claude-profile-clone
fi   # compdef available
