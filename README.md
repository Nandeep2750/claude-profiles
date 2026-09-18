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

## Install

```sh
git clone <your-repo> ~/.claude-profiles     # or copy the folder over
sh ~/.claude-profiles/install.sh             # macOS, Linux, WSL, Git-Bash
```

Native Windows PowerShell:

```powershell
pwsh -File $HOME\.claude-profiles\install.ps1
```

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
~/.claude-profiles/
  bin/claude-profiles.py         all logic, cross-platform
  shell/claude-profiles.zsh      zsh functions + completion
  shell/claude-profiles.bash     bash functions + completion
  shell/ClaudeProfiles.psm1      PowerShell module
  install.sh  install.ps1
  <profile-name>/                one dir per account (do NOT commit these)
```

## Syncing to another machine

Commit `bin/`, `shell/`, `install.*` and this README. Never commit the profile
directories - they hold credentials, session transcripts and machine-local
config. A `.gitignore` is included that excludes them by default.

Credentials do not transfer: run `/login` once per profile on each machine.
On macOS the Keychain entry is keyed to the profile's absolute path, so keeping
the same username/home path across machines avoids surprises.

## Uninstall

Remove the `source` line from your rc file and delete `~/.claude-profiles`.
Your original account in `~/.claude` is never touched by any of this.
