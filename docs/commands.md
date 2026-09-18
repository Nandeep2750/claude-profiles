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
| `claude-profile-remove` | `claude-profiles.py remove` |
| - | `claude-profiles.py path NAME` |

PowerShell users get the same names as aliases, plus verb-noun forms
(`Set-ClaudeProfile`, `Get-ClaudeProfiles`, `Get-ClaudeSessions`,
`Move-ClaudeSession`, `Remove-ClaudeProfile`).

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

List every profile, which account is signed into it, whether credentials are
present, and how much of each account's usage limit is consumed.

```
╭───────────┬─────────────────────┬──────┬────────┬───────────┬───────┬───────────┬────────────╮
│ PROFILE   │ ACCOUNT             │ AUTH │ 5-HOUR │ RESETS    │ 7-DAY │ RESETS    │      AS OF │
├───────────┼─────────────────────┼──────┼────────┼───────────┼───────┼───────────┼────────────┤
│ * default │ you@example.com     │ ok   │    59% │ in 53m    │   40% │ in 4d 23h │     1h ago │
│   work    │ you@company.com     │ ok   │     3% │ in 1h 13m │   87% │ in 2d 18h │     2h ago │
│   client  │ (not logged in)     │ none │      - │ -         │     - │ -         │ never used │
╰───────────┴─────────────────────┴──────┴────────┴───────────┴───────┴───────────┴────────────╯
```

| Column | Meaning |
|---|---|
| `*` | active in this shell |
| `ACCOUNT` | email read from that profile's `.claude.json` |
| `AUTH` | `ok` if credentials exist, `none` if `/login` is still needed |
| `5-HOUR` | percent of the rolling 5-hour limit used, and when it resets |
| `7-DAY` | percent of the weekly limit used, and when it resets |
| `AS OF` | how old the usage figures are |

Percentages are colour-coded: green below 75%, amber from 75%, red from 90%.
A `locked` cell means that limit is currently exhausted.

There are **two independent limits** with separate clocks, which is why both get
their own reset column. An account can be fine on one and nearly out on the
other - the example above shows `work` at 3% for the next five hours but 87%
through its week.

| Flag | Effect |
|---|---|
| `--dirs` | also show each profile's config directory |
| `--no-usage` | hide the usage columns |
| `--plain` | no borders - easier to pipe into `awk`, `grep` or a script |
| `--live` | fetch current figures from the API instead of using the cache |

### Live figures

```sh
claude-profiles --live
```

Fetches each signed-in profile's current usage directly, in parallel, and shows
`live` in the `AS OF` column. This costs **no model tokens** - it reads a usage
endpoint, it does not run a prompt.

Any profile whose fetch fails silently falls back to its cached snapshot, marked
`(cached)`, so the table always renders. A note below the table says whether any
profile fell back.

!!! note "What this sends, and where"
    `--live` reads that profile's OAuth token from your Keychain (macOS) or its
    `.credentials.json` (elsewhere) and sends it to `api.anthropic.com` - the
    same host Claude Code already authenticates against. Nothing is sent
    anywhere else, and nothing is written to disk.

!!! warning "Unofficial endpoint"
    The usage endpoint is internal to Claude Code and is not a documented public
    API. It may change or disappear in any release, which is why the cache
    remains the default and `--live` degrades to it rather than failing.

### Why the cache is stale



!!! warning "Read the AS OF column"
    Without `--live`, figures come from a cache Claude Code writes only when
    **that profile runs**, and it refuses to refetch more than once every five
    minutes. A profile you have not used today shows figures from whenever you
    last used it; one that has never run shows `never used`.

The `AS OF` value turns amber once the snapshot is more than a day old.

The cache stays the default because it is instant and needs no network. Reach
for `--live` when the numbers actually matter - deciding which account to start
a long session on, for instance.

Two accounts showing `ok` at once is normal and expected - that is the whole
point. See [How it works](how-it-works.md) for where credentials live per OS.

---

## `claude-sessions [options]`

List conversations readably, so you can identify one by what it was about
rather than by a 36-character id.

```
╭───┬────────┬───────┬──────────────────────────────────────┬──────────────────────────────────╮
│ # │ WHEN   │ TURNS │ SESSION ID                           │ SUMMARY                          │
├───┼────────┼───────┼──────────────────────────────────────┼──────────────────────────────────┤
│ 1 │ 2m ago │    18 │ eb82f424-4aff-43eb-a0e1-f1e130553fc6 │ refactor the auth middleware…    │
│ 2 │ Sep 11 │     2 │ 2c24a68b-8411-4bb6-9072-99b86b5ae909 │ cant able to take pull           │
╰───┴────────┴───────┴──────────────────────────────────────┴──────────────────────────────────╯
```

The table adapts to your terminal: on a narrow one the `SESSION ID` column
shortens to an 8-character `ID`, which is still enough for `claude-handoff`
since it accepts prefixes.

Defaults to the current directory and the active profile, newest first.

| Flag | Effect |
|---|---|
| `-a`, `--all` | every directory, not just the current one. Adds a dim `~/path (branch)` line under each row |
| `-A`, `--all-profiles` | scan every profile. Adds a `PROFILE` column |
| `-p NAME`, `--profile NAME` | one specific profile |
| `-n N`, `--limit N` | max rows (default 20). Bare `--limit` means no limit |
| `-f`, `--full` | wrap long summaries instead of truncating them |
| `-d DIR`, `--dir DIR` | filter on a directory other than the current one |
| `--plain` | no borders - easier to pipe into other tools |

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

## `claude-profiles doctor`

Checks the installation and reports anything wrong. Also available as
`claude-doctor`.

```
environment
  ok   python3 found at /usr/bin/python3
  ok   claude found at /usr/local/bin/claude
  ok   CLAUDE_CONFIG_DIR unset (profile 'default')
  ok   account data at ~/.claude-profiles (not a git repo)

shell wiring
  ok   .zshrc -> claude-profiles.zsh

profiles
  ok   default: you@example.com
  warn work: not logged in - run 'claude-profile work' then /login

keychain
  ok   Claude Code-credentials
  FAIL Claude Code-credentials-1a2b3c4d is orphaned - no profile maps to it

project markers
  ok   ~/Projects/Acme/.claude-profile -> work

1 problem(s), 1 warning(s)
```

What it checks:

| Area | Looks for |
|---|---|
| environment | `python3` and `claude` on `PATH`; `CLAUDE_CONFIG_DIR` pointing somewhere real; account data not accidentally turned into a git repo |
| shell wiring | exactly one `source` line per rc file, pointing at a file that exists |
| profiles | which are signed in; `.credentials.json` not readable by other users |
| keychain | macOS entries that no longer map to any profile - the residue of deleting a profile with `rm -rf` |
| project markers | `.claude-profile` files that are empty or name a profile that does not exist |

Exits non-zero if it finds problems, so it works in a script. Warnings alone
exit zero - "not logged in" is a normal state, not a fault.

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
orphaned Keychain entry behind. This command removes both.

It also resets your current shell to `default` if you delete the profile you are
standing in, so you are not left pointing at a directory that no longer exists.

**Guards.** It refuses to delete `default` - your original `~/.claude` - and
refuses unknown names, listing what is available instead.

!!! danger "This is not recoverable"
    Every conversation in that profile is deleted with it. If you want to keep
    one, [hand it off](guides/handoff.md) to another profile first:
    `claude-handoff default <session-id>`.

---

## `claude-profiles.py path NAME`

Print a profile's config directory. Useful in scripts.

```sh
CLAUDE_CONFIG_DIR=$(claude-profiles.py path work) claude -p "summarise this repo"
```

That form runs a single command under a profile without switching your shell.
