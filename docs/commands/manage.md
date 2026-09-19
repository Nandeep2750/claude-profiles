# Managing profiles

Setting a profile up, running one command under it, and deleting it.

---

## `claude-profile-clone SOURCE TARGET`

Copy configuration from one profile into another, so a new profile does not
start from nothing.

```sh
claude-profile-clone default work
claude-profile-clone default work --force    # overwrite what is already there
```

| Copied | Never copied |
|---|---|
| `settings.json`, `CLAUDE.md` | `.credentials.json` - belongs to one account |
| `plugins/`, `skills/`, `agents/`, `commands/` | `.claude.json` - account identity and per-project state |
| | `projects/`, `sessions/`, `history.jsonl` - conversation history |

Anything already present in the target is left alone unless you pass `--force`,
and the command tells you what it skipped.

!!! note "Global MCP servers are not cloned"
    They live in `.claude.json` alongside account identity, so copying that file
    would carry the wrong account with it. Re-add them under the new profile:
    `claude-profile work && claude mcp add ...`

---

---

## `claude-profile-exec PROFILE COMMAND [ARGS...]`

Run a single command under a profile without switching your shell.

```sh
claude-profile-exec work claude -p "summarise this repo"
claude-profile-exec client claude mcp list
```

The profile applies only to that command. Your shell's own profile is unchanged,
so this is the right tool for scripts, cron jobs, and one-off checks against
another account.

Exits 2 with a usage message if you omit the command, and 1 if the profile does
not exist.

---

---

## `claude-profile-remove NAME`

Delete a profile: its directory, its conversations, and its stored credentials.

```sh
claude-profile-remove client
```

It shows what will be destroyed and asks you to type the profile name to
confirm:

```
about to permanently delete profile client
  directory : ~/.claude-profiles/client  (12.4MB)
  account   : you@company.com
  sessions  : 37 conversation(s) - deleted with it
  keychain  : Claude Code-credentials-fd54d734

type the profile name to confirm:
```

| Flag | Effect |
|---|---|
| `-y`, `--yes` | skip the confirmation prompt (for scripts) |

**Why not just `rm -rf`?** On macOS, credentials live in the Keychain rather
than in the profile directory. Deleting the directory by hand leaves an
left behind Keychain entry behind. This command removes both.

It also resets your current shell to `default` if you delete the profile you are
standing in, so you are not left pointing at a directory that no longer exists.

**Guards.** It refuses to delete `default` - your original `~/.claude` - and
refuses unknown names, listing what is available instead.

!!! danger "This is not recoverable"
    Every conversation in that profile is deleted with it. If you want to keep
    one, [hand it off](../guides/handoff.md) to another profile first:
    `claude-handoff default <session-id>`.

---
