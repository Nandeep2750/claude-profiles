# Claude Code multi-account profiles - zsh
# Source this from ~/.zshrc:  source ~/.claude-profiles/shell/claude-profiles.zsh
: ${CLAUDE_PROFILE_HOME:="${HOME}/.claude-profiles"}
export CLAUDE_PROFILE_HOME
: ${CLAUDE_PROFILE_PY:="${CLAUDE_PROFILE_HOME}/bin/claude-profiles.py"}
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
claude-profiles() { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" status "$@" }
claude-sessions() { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" sessions "$@" }
claude-handoff()  { "$CLAUDE_PY" "$CLAUDE_PROFILE_PY" handoff  "$@" }

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
  claude-profile "${name:-default}"
}
autoload -Uz add-zsh-hook
add-zsh-hook chpwd  _claude_profile_auto
add-zsh-hook precmd _claude_profile_auto

# completion
if [[ -z "${_comps[compdef]}" ]] && ! whence compdef >/dev/null; then
  autoload -Uz compinit
  compinit -d "${XDG_CACHE_HOME:-$HOME/.cache}/zcompdump-$ZSH_VERSION"
fi
zstyle ':completion:*' menu select
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}'
zstyle ':completion:*:descriptions' format '%F{yellow}%d%f'

_claude_profile_names() {
  local -a names
  names=( default ${(f)"$(ls -1 "$CLAUDE_PROFILE_HOME" 2>/dev/null | grep -v '^\(bin\|shell\)$')"} )
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
