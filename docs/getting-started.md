# Getting started

## Requirements

- [Claude Code](https://claude.com/claude-code) on your `PATH`
- `python3`
- zsh, bash, or PowerShell

## Install

=== "macOS / Linux / WSL"

    ```sh
    git clone https://github.com/Nandeep2750/claude-profiles.git ~/.claude-tools
    sh ~/.claude-tools/install.sh
    ```

=== "Windows (PowerShell)"

    ```powershell
    git clone https://github.com/Nandeep2750/claude-profiles.git $HOME\.claude-tools
    pwsh -File $HOME\.claude-tools\install.ps1
    ```

=== "SSH"

    ```sh
    git clone git@github.com:Nandeep2750/claude-profiles.git ~/.claude-tools
    sh ~/.claude-tools/install.sh
    ```

Restart your shell afterwards:

```sh
exec $SHELL -l
```

The installer detects zsh vs bash, backs up any rc file it edits, and is safe to
re-run - it will not add duplicate lines.

!!! tip "Clone anywhere"
    The shell layers locate everything relative to their own path, so the clone
    location is not hardcoded. Set `CLAUDE_PROFILE_HOME` before installing to
    put account data somewhere other than `~/.claude-profiles`.

!!! warning "Multiple GitHub accounts on one machine?"
    Plain `git@github.com:` uses whichever identity your `~/.ssh/config` maps to
    that host. If it resolves to a different account the clone fails with
    *"Could not read from remote repository"*. Use the matching host alias, or
    clone over HTTPS.

## Your first profile

```sh
claude-profile work      # creates ~/.claude-profiles/work on first use
claude                   # then type /login
```

Your existing account is untouched - it stays available as `default`.

```sh
claude-profiles
```

```
╭──────────┬─────────────────┬──────┬────────┬───────────┬───────┬───────────┬─────────╮
│ PROFILE  │ ACCOUNT         │ AUTH │ 5-HOUR │ RESETS    │ 7-DAY │ RESETS    │   AS OF │
├──────────┼─────────────────┼──────┼────────┼───────────┼───────┼───────────┼─────────┤
│ * work   │ you@company.com │ ok   │     3% │ in 1h 13m │    7% │ in 2d 18h │  2m ago │
│   default│ you@example.com │ ok   │    59% │ in 53m    │   40% │ in 4d 23h │  1h ago │
╰──────────┴─────────────────┴──────┴────────┴───────────┴───────┴───────────┴─────────╯
```

Both signed in at once. Switching logs nothing out.

## Two directories, kept apart

| Path | Holds | Synced |
|---|---|---|
| `~/.claude-tools` | logic, shell layers, installers | yes - this is the repo |
| `~/.claude-profiles` | credentials, transcripts, per-account config | **never** |

Only tooling is version-controlled. Account data stays machine-local: run
`/login` once per profile on each machine. A laptop might have only `personal`
while a work desktop has all three.

Both directories are created for you. `install.sh` creates
`~/.claude-profiles`; `claude-profile NAME` creates each profile inside it.

Profiles also share nothing with each other - MCP servers, plugins, settings and
conversation history are all per-profile. See
[What's shared, what isn't](isolation.md) before you wonder where your MCP
servers went.

!!! danger "Do not move a profile directory after logging in"
    On macOS the Keychain entry is keyed to the profile's absolute path, so
    moving it invalidates the credentials and forces a re-login.

## Next steps

- [Add an account](guides/add-an-account.md)
- [Per-project accounts](guides/per-project.md) - switch automatically on `cd`
- [Session handoff](guides/handoff.md) - continue a conversation on another account
- [What's shared, what isn't](isolation.md) - why a new profile starts empty

## See which profile you are on

Two one-off settings worth doing now, so you never use the wrong account by
accident:

```sh
claude-profiles statusline --install-all    # inside Claude Code sessions
```

```sh
echo 'export CLAUDE_PROFILE_PROMPT=1' >> ~/.zshrc   # in your shell prompt
```

The prompt indicator must be set **before** the line that sources the shell
layer. Both are covered in [Settings](settings.md#knowing-which-profile-is-active).

## Uninstall

Remove the `source` line from your rc file and delete `~/.claude-tools`.
Deleting `~/.claude-profiles` additionally logs out every extra account.
Your original account in `~/.claude` is never touched by any of this.
