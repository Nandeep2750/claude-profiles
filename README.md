# Claude Code multi-account profiles

Run several Claude accounts on one machine, pick one per project, and hand a
session from one account to another when the first hits its rate limit.

## How it works

Claude Code reads `CLAUDE_CONFIG_DIR`. Each distinct value gets its own
credential slot, so profiles stay logged in at the same time:

| OS | Where credentials live |
|---|---|
| macOS | Keychain, service `Claude Code-credentials-<sha256(dir)[:8]>` |
| Linux / WSL / Windows | `<profile dir>/.credentials.json` |

Each profile also gets its own `.claude.json`, `settings.json`, MCP servers and
session history. Nothing here patches Claude Code - it only sets an env var and
copies transcript files.

## Two directories, kept apart

| Path | Holds | Synced? |
|---|---|---|
| `~/.claude-tools` (this repo) | logic, shell layers, installers | yes - this is what you clone |
| `~/.claude-profiles` | credentials, transcripts, per-account config | **never** |

Only the tooling is version-controlled. Account data stays machine-local: run
`/login` once per profile on each machine.

On macOS a profile's Keychain entry is keyed to its **absolute path**, so do not
move or rename profile directories after logging in - it invalidates the
credentials and forces a re-login.

## Install

```sh
git clone git@github.com:nandeep-biztech/claude-profiles.git ~/.claude-tools
sh ~/.claude-tools/install.sh        # macOS, Linux, WSL, Git-Bash
```

HTTPS instead, if the machine has no SSH key set up yet:

```sh
git clone https://github.com/nandeep-biztech/claude-profiles.git ~/.claude-tools
```

> **Multiple GitHub accounts on one machine?** Plain `git@github.com:` uses
> whichever identity your `~/.ssh/config` maps to that host. If it resolves to a
> different account, the clone or push fails with *"Could not read from remote
> repository"*. Use the matching host alias instead, e.g.
> `git clone github-biztech:nandeep-biztech/claude-profiles.git ~/.claude-tools`,
> or fix an existing clone with
> `git remote set-url origin github-biztech:nandeep-biztech/claude-profiles.git`.

Native Windows PowerShell:

```powershell
pwsh -File $HOME\.claude-tools\install.ps1
```

The installer wires a `source` line into your rc file pointing at wherever you
cloned it - no path is hardcoded. Set `CLAUDE_PROFILE_HOME` first if you want
account data somewhere other than `~/.claude-profiles`.

Requires `python3` and `claude` on PATH. Restart your shell afterwards.
The installer backs up any rc file it edits and is safe to re-run.

## Commands

```sh
claude-profiles                 # every profile + which account is in it
claude-profile                  # which profile is active here
claude-profile work             # switch (creates it on first use)
claude-profile default          # back to the original ~/.claude
claude-sessions                 # sessions for this dir, readable
claude-sessions -A -a --full    # every profile, every dir, untruncated
claude-handoff work             # copy this dir's latest session to `work`
claude-handoff work 0a9014e8    # ...or a specific session (prefix is enough)
```

## Add an account

```sh
claude-profile work
claude            # then /login
```

## Per-project auto-switch

Put a `.claude-profile` file containing a profile name anywhere in a project
tree. The nearest one wins, walking up from the current directory:

```sh
echo work > ~/Projects/Acme/.claude-profile   # covers every repo under Acme/
```

Anything with no marker falls back to `default`.

## Hitting a rate limit mid-session

```sh
claude-handoff work             # prints the resume command
claude-profile work
claude --resume <id>
```

The transcript is copied, not moved, so the original account keeps its copy.
Your project directory is untouched - only the billing account changes.
Resuming re-sends the conversation, so the first turn on the new account is a
cold cache and costs more tokens than a normal continuation.

## Layout

```
~/.claude-tools/                 <- this repo
  bin/claude-profiles.py         all logic, cross-platform
  shell/claude-profiles.zsh      zsh functions + completion
  shell/claude-profiles.bash     bash functions + completion
  shell/ClaudeProfiles.psm1      PowerShell module
  install.sh  install.ps1

~/.claude-profiles/              <- account data, machine-local
  <profile-name>/                one dir per account
```

## Uninstall

Remove the `source` line from your rc file and delete `~/.claude-tools`.
Deleting `~/.claude-profiles` additionally logs out every extra account.
Your original account in `~/.claude` is never touched by any of this.
