# Commands

Fifteen commands, grouped by what you are trying to do. Every one works the
same way on macOS, Linux, WSL and Windows.

<div class="grid cards" markdown>

-   :material-swap-horizontal: **[Switching profiles](profiles.md)**

    ---

    Move between accounts, and see which one is active.

    `claude-profile` · `claude-profiles`

-   :material-gauge: **[Usage and limits](usage.md)**

    ---

    How much of each account is left, and which has the most room.

    `--live` · `claude-best` · `claude-auto`

-   :material-message-text: **[Sessions](sessions.md)**

    ---

    Find past conversations, move one to another account, clear out old ones.

    `claude-sessions` · `claude-handoff` · `claude-prune`

-   :material-folder-cog: **[Managing profiles](manage.md)**

    ---

    Set a profile up, run one command under it, or delete it.

    `claude-profile-clone` · `-exec` · `-remove`

-   :material-dock-bottom: **[Status line](statusline.md)**

    ---

    See the active account from inside a Claude Code session.

    `claude-profiles statusline`

-   :material-medical-bag: **[Health and updates](maintenance.md)**

    ---

    Check the install, and move to a newer version.

    `claude-doctor` · `claude-update`

</div>

## Every command

| Command | Does |
|---|---|
| [`claude-profile NAME`](profiles.md#claude-profile-name) | Switch this shell to a profile, creating it if needed |
| [`claude-profiles`](profiles.md#claude-profiles) | Every profile, its account, and how much of its limits are used |
| [`claude-profiles --live`](usage.md#live-figures) | The same, with current figures instead of the cache |
| [`claude-sessions`](sessions.md#claude-sessions-options) | List conversations readably |
| [`claude-sessions --grep`](sessions.md#searching-your-conversations) | Search every message across every account |
| [`claude-handoff NAME`](sessions.md#claude-handoff-target-session) | Copy a conversation to another account and continue there |
| [`claude-best`](usage.md#claude-best) | Which account has the most headroom |
| [`claude-auto`](usage.md#claude-auto) | Launch Claude on that account automatically |
| [`claude-profile-exec`](manage.md#claude-profile-exec-profile-command-args) | Run one command under a profile without switching |
| [`claude-profile-clone`](manage.md#claude-profile-clone-source-target) | Seed a new profile's settings from an existing one |
| [`claude-profile-remove`](manage.md#claude-profile-remove-name) | Delete a profile, its history and its credentials |
| [`claude-prune`](sessions.md#claude-prune) | Delete old transcripts (dry run by default) |
| [`claude-doctor`](maintenance.md#claude-profiles-doctor) | Check the installation for problems |
| [`claude-update`](maintenance.md#claude-update) | Check for and pull a newer version |
| [`claude-profiles statusline`](statusline.md#claude-profiles-statusline) | A status line for inside Claude Code |

Names used throughout these examples - `default`, `work`, `client` - are
placeholders. Profiles can be called anything.

---
---

## How the commands are built

Shell commands wrap one cross-platform Python core
(`bin/claude-profiles.py`). The core can also be called directly - useful in
scripts, or on a shell with no wrapper installed.

| Shell command | Core equivalent |
|---|---|
| `claude-profile NAME` | *(shell only - it must export into your session)* |
| `claude-profiles` | `claude-profiles.py status` |
| `claude-sessions` | `claude-profiles.py sessions` |
| `claude-handoff` | `claude-profiles.py handoff` |
| `claude-profile-remove` | `claude-profiles.py remove` |
| `claude-profile-clone` | `claude-profiles.py clone` |
| `claude-profile-exec` | *(shell only)* |
| `claude-doctor` | `claude-profiles.py doctor` |
| `claude-prune` | `claude-profiles.py prune` |
| `claude-best` | `claude-profiles.py best` |
| `claude-update` | `claude-profiles.py update` |
| `claude-auto` | *(shell only)* |
| - | `claude-profiles.py path NAME` |

PowerShell users get the same names as aliases, plus verb-noun forms
(`Set-ClaudeProfile`, `Get-ClaudeProfiles`, `Get-ClaudeSessions`,
`Move-ClaudeSession`, `Remove-ClaudeProfile`, `Test-ClaudeProfiles`,
`Copy-ClaudeProfile`, `Invoke-ClaudeProfile`).

---

---

## Calling the core directly

Every shell command is a thin wrapper around `bin/claude-profiles.py`. You can
call it yourself - useful in scripts, or on a machine where the shell layer is
not installed.

## `claude-profiles.py path NAME`

Print a profile's config directory. Useful in scripts.

```sh
CLAUDE_CONFIG_DIR=$(claude-profiles.py path work) claude -p "summarise this repo"
```

That form runs a single command under a profile without switching your shell.
