---
hide:
  - navigation
---

# claude-profiles

**Run multiple Claude Code accounts on one machine.** Pick an account per
project, and move a conversation between accounts when one hits its usage limit.

[Get started](getting-started.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/Nandeep2750/claude-profiles){ .md-button }

---

## Why

Claude Code stores one login. Signing into a second account logs the first one
out, and each account can only see its own conversation history. That hurts in
three ways:

<div class="grid cards" markdown>

-   **Work and personal accounts**

    ---

    Constant re-authentication to move between them. With profiles, both stay
    signed in and switching is instant.

-   **Usage limits**

    ---

    You stop dead mid-conversation even when another account has capacity.
    [Session handoff](guides/handoff.md) lets you continue where you left off.

-   **Wrong account by accident**

    ---

    Easy to do on a client project. A [marker file](guides/per-project.md)
    selects the right account when you `cd` into the repo.

</div>

## Quick start

```sh
git clone https://github.com/Nandeep2750/claude-profiles.git ~/.claude-tools
sh ~/.claude-tools/install.sh
exec $SHELL -l
```

```sh
claude-profile work      # create + switch to a profile named "work"
claude                   # then /login with that account
claude-profiles          # see every profile and who is signed into it
```

```
╭───────────┬─────────────────────┬──────┬────────┬───────────┬───────┬───────────┬────────────╮
│ PROFILE   │ ACCOUNT             │ AUTH │ 5-HOUR │ RESETS    │ 7-DAY │ RESETS    │      AS OF │
├───────────┼─────────────────────┼──────┼────────┼───────────┼───────┼───────────┼────────────┤
│ * default │ you@example.com     │ ok   │    59% │ in 53m    │   40% │ in 4d 23h │     1h ago │
│   work    │ you@company.com     │ ok   │     3% │ in 1h 13m │   87% │ in 2d 18h │     2h ago │
│   client  │ (not logged in)     │ none │      - │ -         │     - │ -         │ never used │
╰───────────┴─────────────────────┴──────┴────────┴───────────┴───────┴───────────┴────────────╯
```

Two accounts signed in at once is normal - that is the whole point. The usage
columns show which one has room before you start, so you are not surprised
mid-conversation. `work` above is fine for the next five hours but 87% through
its week.

!!! info "Profiles share nothing"
    Each profile is a complete, separate copy of Claude Code's configuration -
    MCP servers, plugins, settings and conversation history included. See
    [What's shared, what isn't](isolation.md).

## How it works, in one line

Claude Code reads `CLAUDE_CONFIG_DIR` and derives its credential slot from that
path, so each profile gets its own login. Nothing here patches Claude Code -
see [How it works](how-it-works.md) for the details.

## Commands

| Command | Does |
|---|---|
| `claude-profiles` | List every profile and which account is signed into it |
| `claude-profile NAME` | Switch to `NAME`, creating it if needed |
| `claude-sessions` | List this directory's conversations, readably |
| `claude-handoff NAME` | Copy this directory's latest conversation to profile `NAME` |
| `claude-profile-remove NAME` | Delete a profile, its conversations and its credentials |

Full flag reference: [Commands](commands.md).

## Supported platforms

macOS, Linux, WSL, Git-Bash, and native Windows PowerShell. Requires `python3`
and [Claude Code](https://claude.com/claude-code).
