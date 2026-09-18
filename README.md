# claude-profiles

Run multiple Claude Code accounts on one machine. Pick one per project, and move
a conversation between accounts when one hits its usage limit.

- **Multiple accounts, signed in at once.** Switching doesn't log anything out.
- **Per-project accounts.** `cd` into a repo, the right account is selected.
- **Session handoff.** Hit a limit mid-conversation? Continue it on another account.
- **Cross-platform.** macOS, Linux, WSL, Git-Bash, native Windows PowerShell.
- **No patching.** It sets one environment variable Claude Code already reads.

## Contents

- [Quick start](#quick-start)
- [The problem this solves](#the-problem-this-solves)
- [Install](#install)
- [Commands](#commands)
- [Guides](#guides)
  - [Add an account](#add-an-account)
  - [Per-project auto-switching](#per-project-auto-switching)
  - [Hand off a session when you hit a limit](#hand-off-a-session-when-you-hit-a-limit)
- [Two directories, kept apart](#two-directories-kept-apart)
- [Further reading](#further-reading)
- [Uninstall](#uninstall)

## Quick start

```sh
git clone git@github.com:nandeep-biztech/claude-profiles.git ~/.claude-tools
sh ~/.claude-tools/install.sh
exec $SHELL -l
```

```sh
claude-profile work      # create + switch to a profile named "work"
claude                   # then /login with that account
claude-profiles          # see every profile and who is signed into it
```

## The problem this solves

Claude Code stores one login. Signing into a second account logs the first one
out, and each account can only see its own conversation history.

That hurts in three ways:

1. **Work and personal accounts** need constant re-authentication.
2. **Usage limits** stop you dead, even when another account has capacity.
3. **Wrong account** is easy to use by accident on a client project.

A *profile* is an isolated Claude Code identity: its own login, settings, MCP
servers and session history. Profiles coexist - switching between them is
instant and logs nothing out.

## Install

Requires `python3` and [Claude Code](https://claude.com/claude-code) on `PATH`.

**macOS / Linux / WSL / Git-Bash**

```sh
git clone git@github.com:nandeep-biztech/claude-profiles.git ~/.claude-tools
sh ~/.claude-tools/install.sh
```

HTTPS instead, if the machine has no SSH key yet:

```sh
git clone https://github.com/nandeep-biztech/claude-profiles.git ~/.claude-tools
```

**Native Windows PowerShell**

```powershell
git clone https://github.com/nandeep-biztech/claude-profiles.git $HOME\.claude-tools
pwsh -File $HOME\.claude-tools\install.ps1
```

Restart your shell afterwards. The installer detects zsh vs bash, backs up any
rc file it edits, and is safe to re-run - it will not add duplicate lines.

Clone anywhere you like; the shell layers locate everything relative to their
own path. Set `CLAUDE_PROFILE_HOME` before installing to put account data
somewhere other than `~/.claude-profiles`.

> **Multiple GitHub accounts on one machine?** Plain `git@github.com:` uses
> whichever identity your `~/.ssh/config` maps to that host. If it resolves to a
> different account the clone fails with *"Could not read from remote
> repository"*. Use the matching host alias, e.g.
> `git clone github-biztech:nandeep-biztech/claude-profiles.git ~/.claude-tools`.

## Commands

| Command | Does |
|---|---|
| `claude-profiles` | List every profile and which account is signed into it |
| `claude-profile` | Show the active profile |
| `claude-profile NAME` | Switch to `NAME`, creating it if needed |
| `claude-profile default` | Switch back to the original `~/.claude` |
| `claude-sessions` | List this directory's conversations, readably |
| `claude-handoff NAME` | Copy this directory's latest conversation to profile `NAME` |

Every command supports tab completion for profile names. Full flag reference:
[docs/commands.md](docs/commands.md).

## Guides

### Add an account

```sh
claude-profile work      # creates ~/.claude-profiles/work on first use
claude                   # then type /login
```

Your existing account is untouched - it stays available as `default`.

Profiles are created by naming them. There is no registry file, so a typo makes
a new empty profile rather than an error. If a profile looks unexpectedly
logged out, run `claude-profiles` and check for a near-miss name.

### Per-project auto-switching

Put a `.claude-profile` file containing a profile name anywhere in a project
tree. The nearest one wins, walking up from the current directory:

```sh
echo work > ~/Projects/Acme/.claude-profile     # covers every repo under Acme/
```

Now `cd` anywhere under `~/Projects/Acme` selects the `work` profile
automatically. Directories with no marker fall back to `default`.

Because the marker sits above the repos it governs, it does not need to be
committed or gitignored.

### Hand off a session when you hit a limit

**What it does, simply:** it copies a conversation from one account to another,
so you can keep going when the first account runs out.

You are 50 messages into a conversation. Claude knows your whole problem. Then:

> You've hit your usage limit.

Your other account has capacity, but Claude Code cannot see this conversation
from there - each account keeps its own separate history.

```sh
claude-handoff work
```

That copies the current conversation into the `work` account's history, then
prints the command to continue it:

```sh
claude-profile work
claude --resume <id>
```

Same conversation, same memory, different account paying. Like forwarding an
email thread to your other address: the thread is identical, only the mailbox
changed.

**What it does not do**

- **Does not move anything.** It is a copy; the original account keeps its version.
- **Does not touch your code.** Same project folder, same files, same git branch.
- **Does not transfer your limit.** That is the point - the other account has its own quota.

**One catch:** run it from the folder you were working in. It finds the
conversation by which folder it belongs to.

```sh
cd ~/Projects/Acme/api
claude-handoff work
```

Pick a specific conversation instead of the latest with `claude-sessions` to
find it, then pass the id (a prefix is enough):

```sh
claude-sessions
claude-handoff work 0a9014e8
```

Resuming re-sends the conversation to the new account, so the first turn there
is a cold cache and costs more tokens than an ordinary continuation.

## Two directories, kept apart

| Path | Holds | Synced |
|---|---|---|
| `~/.claude-tools` (this repo) | logic, shell layers, installers | yes - this is what you clone |
| `~/.claude-profiles` | credentials, transcripts, per-account config | **never** |

Only tooling is version-controlled. Account data stays machine-local: run
`/login` once per profile on each machine. A laptop might have only `personal`
while a work desktop has all three - nothing about the profile list is stored
in this repo.

Both directories are created for you. `install.sh` creates
`~/.claude-profiles`; `claude-profile NAME` creates each profile inside it.

> **Do not move or rename a profile directory after logging in.** On macOS the
> Keychain entry is keyed to the profile's absolute path, so moving it
> invalidates the credentials and forces a re-login.

## Further reading

- [docs/commands.md](docs/commands.md) - every command and flag, with examples
- [docs/how-it-works.md](docs/how-it-works.md) - the mechanism, storage layout, per-OS differences
- [docs/troubleshooting.md](docs/troubleshooting.md) - common problems and fixes

## Uninstall

Remove the `source` line from your rc file and delete `~/.claude-tools`.
Deleting `~/.claude-profiles` additionally logs out every extra account.
Your original account in `~/.claude` is never touched by any of this.
