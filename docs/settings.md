# Settings

Everything is configured through environment variables, set in your rc file
**before** the `source` line that loads the shell layer.

## How a profile gets chosen

Before the variables, the rule they fit into. On every `cd` - and before the
first prompt of a new terminal - the shell layer walks **up** from the current
directory looking for a `.claude-profile` file:

```
~/projects/<project-name>/api/src    no marker, go up
~/projects/<project-name>/api        no marker, go up
~/projects/<project-name>            .claude-profile -> "work"   <- first match wins
```

1. The nearest `.claude-profile` walking upward, if there is one.
2. Otherwise `CLAUDE_DEFAULT_PROFILE`, if you set it.
3. Otherwise `default`, the original `~/.claude`.

So markers answer *"in this project, use that account"*, and
`CLAUDE_DEFAULT_PROFILE` answers *"and everywhere else, use this one"*.

### Marking a project

Create the file in any directory - a single repo, or a folder containing
several:

```sh
echo work > ~/projects/<project-name>/.claude-profile
```

It contains nothing but a profile name. From then on, `cd` anywhere at or below
that directory selects `work` automatically, and `claude` uses that account
without you switching anything.

```
~/projects/<project-name>/          .claude-profile -> "work"
  ├── api/                       -> work
  ├── web/                       -> work
  └── infra/                     -> work
```

Putting it one level **above** your repos, as here, covers all of them from one
file and keeps it outside version control - nothing to commit or gitignore. Put
it inside a repo instead if only that repo should differ.

A deeper marker beats a shallower one, so a single repo can opt out of its
parent's rule:

```sh
echo personal > ~/projects/<project-name>/experiment/.claude-profile
```

Markers are just files. Delete one to remove the rule, or `cat` one to see it.
`claude-doctor` reports any that name a profile which does not exist.

See [Per-project accounts](guides/per-project.md) for the full guide.

## `CLAUDE_DEFAULT_PROFILE`

Which profile an **unmarked** directory falls back to. Defaults to `default`,
i.e. the original `~/.claude`.

```sh
export CLAUDE_DEFAULT_PROFILE=work
source "$HOME/.claude-tools/shell/claude-profiles.zsh"
```

Set it before the `source` line, in `~/.zshrc` or `~/.bashrc`.

This is the machine-wide fallback, not a per-project setting - it applies
wherever no marker matches.

It is worth setting when `default` is not the account you want to land on - after
logging out of it, for instance, or if your original `~/.claude` belongs to an
account you rarely use.

!!! tip "A marker always wins"
    Setting this does not disturb directories that already have a
    `.claude-profile`. It only changes what happens everywhere else.

If you would rather not set an environment variable, a marker at your home
directory does much the same job:

```sh
echo work > ~/.claude-profile
```

The difference is small. The variable applies wherever your rc file is loaded. A
marker at `~` is a real file, so anything walking upward finds it too.

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
[command reference](commands/statusline.md#claude-profiles-statusline). Settings are
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
