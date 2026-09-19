# Settings

Everything is configured through environment variables, set in your rc file
**before** the `source` line that loads the shell layer.

## `CLAUDE_DEFAULT_PROFILE`

Which profile a directory with no `.claude-profile` marker falls back to.
Defaults to `default`, i.e. the original `~/.claude`.

```sh
export CLAUDE_DEFAULT_PROFILE=work
source "$HOME/.claude-tools/shell/claude-profiles.zsh"
```

Useful when your original `~/.claude` is not the account you actually want as a
fallback - after logging out of it, for instance. A `.claude-profile` marker
always wins over this.

## `CLAUDE_PROFILE_PROMPT`

Show the active profile in your prompt, so you cannot use the wrong account by
accident.

```sh
export CLAUDE_PROFILE_PROMPT=1
source "$HOME/.claude-tools/shell/claude-profiles.zsh"
```

zsh appends it to `RPROMPT`; bash prepends it to `PS1`. It stays quiet on
`default` so your prompt is only marked when you are somewhere unusual.

| Variable | Effect |
|---|---|
| `CLAUDE_PROFILE_PROMPT=1` | turn the indicator on |
| `CLAUDE_PROFILE_PROMPT_PREFIX` | text before the name (default `claude:`) |
| `CLAUDE_PROFILE_SHOW_DEFAULT=1` | also show it while on `default` |

Building your own prompt? Call `claude_profile_prompt` directly - it prints the
indicator or nothing, and touches no other state.

```sh
PROMPT='%~ $(claude_profile_prompt) %# '
```

## Knowing which profile is active

Two indicators cover two different places, and you probably want both:

| Where you are | What tells you | Set up with |
|---|---|---|
| Your shell | the prompt indicator | `CLAUDE_PROFILE_PROMPT=1`, above |
| Inside a Claude Code session | the status line | `claude-profiles statusline --install-all` |

The shell prompt disappears the moment Claude Code takes over the terminal,
which is exactly when knowing the account matters most - so the status line is
not a duplicate of it.

```sh
claude-profiles statusline --install-all
```

```
work │ you@company.com │ ⎇ main │ ctx 52%/1000k │ 5h 2% │ 7d 3%
```

Choose what it shows with `--show`; the segments are listed in the
[command reference](commands.md#claude-profiles-statusline). Settings are
per-profile, which is why `--install-all` exists.

## `CLAUDE_PROFILE_HOME`

Where account data lives. Defaults to `~/.claude-profiles`. Set it before
running `install.sh` if you want it elsewhere.

## `CLAUDE_CONFIG_DIR`

Read by Claude Code itself, not by this tool - `claude-profile` sets it for you.
Setting it by hand works too, and `claude-doctor` warns if it points somewhere
that does not exist.

## `NO_COLOR`

Honoured by every command. Output is also uncoloured automatically when piped.
