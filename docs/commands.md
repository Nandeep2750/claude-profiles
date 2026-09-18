# Command reference

Four shell commands wrap one cross-platform Python core
(`bin/claude-profiles.py`). The core can also be called directly - useful in
scripts, or on a shell with no wrapper installed.

| Shell command | Core equivalent |
|---|---|
| `claude-profile NAME` | *(shell only - it must export into your session)* |
| `claude-profiles` | `claude-profiles.py status` |
| `claude-sessions` | `claude-profiles.py sessions` |
| `claude-handoff` | `claude-profiles.py handoff` |
| - | `claude-profiles.py path NAME` |

PowerShell users get the same names as aliases, plus verb-noun forms
(`Set-ClaudeProfile`, `Get-ClaudeProfiles`, `Get-ClaudeSessions`,
`Move-ClaudeSession`).

---

## `claude-profile [NAME]`

Switch the current shell to a profile. With no argument, reports the active one.

```sh
claude-profile             # which profile am I on?
claude-profile work        # switch to "work" (created if it does not exist)
claude-profile default     # back to the original ~/.claude
```

Sets `CLAUDE_CONFIG_DIR` and `CLAUDE_PROFILE_NAME` in the current shell. It is a
shell function rather than a script because only a function can modify the
environment of the shell you are sitting in.

**Scope is per-shell.** Two terminal tabs can be on different accounts at the
same time. An already-running `claude` is unaffected - the variable is read at
launch, so restart it after switching.

`default` is a reserved name meaning "no `CLAUDE_CONFIG_DIR` set", i.e. the
stock `~/.claude`. It is not a directory under `~/.claude-profiles`.

---

## `claude-profiles`

List every profile, which account is signed into it, and whether credentials
are present.

```
   PROFILE  CONFIG DIR                        ACCOUNT                  AUTH
*  default  ~/.claude                         you@example.com          ok
   work     ~/.claude-profiles/work           you@company.com          ok
   client   ~/.claude-profiles/client         (not logged in)          none
```

| Column | Meaning |
|---|---|
| `*` | active in this shell |
| `ACCOUNT` | email read from that profile's `.claude.json` |
| `AUTH` | `ok` if credentials exist, `none` if `/login` is still needed |

Two accounts showing `ok` at once is normal and expected - that is the whole
point. See [how-it-works.md](how-it-works.md) for where credentials live per OS.

---

## `claude-sessions [options]`

List conversations readably, so you can identify one by what it was about
rather than by a 36-character id.

```
   WHEN      TURNS  SESSION ID                            SUMMARY
 1 2m ago       18  eb82f424-4aff-43eb-a0e1-f1e130553fc6  how do I set up two accounts…
 2 Sep 11        2  2c24a68b-8411-4bb6-9072-99b86b5ae909  cant able to take pull
```

Defaults to the current directory and the active profile, newest first.

| Flag | Effect |
|---|---|
| `-a`, `--all` | every directory, not just the current one. Adds a dim `~/path (branch)` line under each row |
| `-A`, `--all-profiles` | scan every profile. Adds a `PROFILE` column |
| `-p NAME`, `--profile NAME` | one specific profile |
| `-n N`, `--limit N` | max rows (default 20). Bare `--limit` means no limit |
| `-f`, `--full` | wrap long summaries instead of truncating them |
| `-d DIR`, `--dir DIR` | filter on a directory other than the current one |

```sh
claude-sessions                   # this directory, active profile
claude-sessions -a                # every directory
claude-sessions -A -a --full      # everything, everywhere, untruncated
claude-sessions -p work -n 50     # 50 most recent in the "work" profile
```

Summaries adapt to terminal width between 40 and 100 characters. `TURNS` counts
your messages, ignoring tool results and sidechains.

---

## `claude-handoff TARGET [SESSION]`

Copy a conversation into another profile so that account can resume it. See the
[guide](guides/handoff.md) for what this is
for; this section is the mechanics.

```sh
claude-handoff work               # this directory's most recent conversation
claude-handoff work 0a9014e8      # a specific one - a prefix is enough
claude-handoff work -s client     # take it from "client" instead of the active profile
claude-handoff work -d ~/code/api # conversations belonging to another directory
```

| Argument | Meaning |
|---|---|
| `TARGET` | profile to copy into. Must already exist |
| `SESSION` | optional session id or unique prefix. Omit for the latest |
| `-s`, `--source` | profile to copy from (default: the active one) |
| `-d`, `--dir` | directory whose conversations to consider (default: current) |

On success it prints the resume command:

```
handed off session 0a9014e8-8806-43cf-98fd-28fad1353923
  from: default   to: work
  dir : ~/Projects/Acme/api

  claude-profile work && claude --resume 0a9014e8-8806-43cf-98fd-28fad1353923
```

**Guards.** An ambiguous prefix lists the matches instead of guessing. Copying a
profile onto itself, or into a profile that does not exist, is refused with a
message rather than silently doing nothing.

It is a copy - the source profile keeps its version, so you can switch back.

---

## `claude-profiles.py path NAME`

Print a profile's config directory. Useful in scripts.

```sh
CLAUDE_CONFIG_DIR=$(claude-profiles.py path work) claude -p "summarise this repo"
```

That form runs a single command under a profile without switching your shell.
