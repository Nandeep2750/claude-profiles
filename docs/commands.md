# Command reference

## At a glance

| Command | Does |
|---|---|
| [`claude-profile NAME`](#claude-profile-name) | Switch this shell to a profile, creating it if needed |
| [`claude-profiles`](#claude-profiles) | Every profile, its account, and how much of its limits are used |
| [`claude-profiles --live`](#live-figures) | The same, with current figures instead of the cache |
| [`claude-sessions`](#claude-sessions-options) | List conversations readably |
| [`claude-sessions --grep`](#searching-your-conversations) | Search every message across every account |
| [`claude-handoff NAME`](#claude-handoff-target-session) | Copy a conversation to another account and continue there |
| [`claude-best`](#claude-best) | Which account has the most headroom |
| [`claude-auto`](#claude-auto) | Launch Claude on that account automatically |
| [`claude-profile-exec`](#claude-profile-exec-profile-command-args) | Run one command under a profile without switching |
| [`claude-profile-clone`](#claude-profile-clone-source-target) | Seed a new profile's settings from an existing one |
| [`claude-profile-remove`](#claude-profile-remove-name) | Delete a profile, its history and its credentials |
| [`claude-prune`](#claude-prune) | Delete old transcripts (dry run by default) |
| [`claude-doctor`](#claude-profiles-doctor) | Check the installation for problems |
| [`claude-update`](#claude-update) | Check for and pull a newer version |
| [`claude-profiles statusline`](#claude-profiles-statusline) | A status line for inside Claude Code |

Names used throughout these examples - `default`, `work`, `client` - are
placeholders. Profiles can be called anything.

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

Any profile whose fetch fails falls back to its cached snapshot **and says
why** in the `AS OF` column, so the table always renders:

| Shown | Meaning |
|---|---|
| `live` | fetched just now |
| `14h ago (token expired)` | the access token has aged out - see below |
| `14h ago (rate limited)` | the usage endpoint returned 429; try again shortly |
| `14h ago (unreachable)` | no network, or the request timed out |
| `14h ago (not logged in)` | no credentials for that profile |

### Expired tokens

Access tokens are short-lived - roughly half a day - and Claude Code refreshes
them whenever it runs. A profile you have not used since its token aged out
returns 401, so `--live` reports `token expired` and falls back.

Open a session under that profile and the token refreshes:

```sh
claude-profile work
claude       # any session refreshes it
```

!!! note "Why this tool does not refresh tokens itself"
    It could, using the stored refresh token - but refresh tokens can rotate,
    and writing a new one back risks desynchronising Claude Code's own copy.
    Reporting the problem is safer than silently competing with Claude Code
    over credential state.

`claude-doctor` also warns about expired tokens, so you can spot them before
they surprise you.

!!! note "What this sends, and where"
    `--live` reads that profile's OAuth token from your Keychain (macOS) or its
    `.credentials.json` (elsewhere) and sends it to `api.anthropic.com` - the
    same host Claude Code already authenticates against. Nothing is sent
    anywhere else, and nothing is written to disk.

!!! warning "Unofficial endpoint"
    The usage endpoint is internal to Claude Code and is not a documented public
    API. It may change or disappear in any release, which is why the cache
    remains the default and `--live` degrades to it rather than failing.

!!! tip "A live fetch is remembered"
    `--live` writes what it fetched beside the profile, so a plain
    `claude-profiles` straight afterwards shows those figures as
    `0m ago` rather than falling back to a much older snapshot.

### Why the cache is stale



!!! warning "Read the AS OF column"
    Without `--live`, figures come from whichever cache is newer: Claude
    Code's, which it writes only when **that profile runs** and refuses to
    refresh more than once every five minutes, or the one `--live` last
    wrote. A profile you have not used today shows figures from whenever you
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
| `-g PATTERN`, `--grep PATTERN` | only sessions containing PATTERN (case-insensitive regex) |

```sh
claude-sessions                   # this directory, active profile
claude-sessions -a                # every directory
claude-sessions -A -a --full      # everything, everywhere, untruncated
claude-sessions -p work -n 50     # 50 most recent in the "work" profile
```

Summaries adapt to terminal width between 40 and 100 characters. `TURNS` counts
your messages, ignoring tool results and sidechains.

### Searching your conversations

```sh
claude-sessions -A -a --grep "rate limit"
```

Searches the full text of every message - **yours and Claude's** - not just the
opening prompt. Sessions that match show the matching passage in place of the
summary, with surrounding context:

```
│ 1 │ work    │ 0m ago │ 55 │ eb82f424… │ ~ │ …gives each profile its own macOS Keychain… │
```

The pattern is a case-insensitive regular expression, so `-g "auth|login"` works.
An invalid pattern exits 2 with the regex error rather than silently matching
nothing.

Combine it with `-A -a` to search every profile and every directory at once -
this is the fastest way to find the conversation where you solved something
months ago.

---

## `claude-handoff TARGET [SESSION]`

Copy a conversation into another profile so that account can resume it. See the
[guide](guides/handoff.md) for what this is
for; this section is the mechanics.

```sh
claude-handoff work               # this directory's most recent conversation
claude-handoff work 0a9014e8      # a specific one - a prefix is enough
claude-handoff work -s client     # take it from "client" instead of the active profile
claude-handoff work -d ~/projects/<project-name>/api # conversations belonging to another directory
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
  dir : ~/projects/<project-name>/api

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
  ok   ~/projects/<project-name>/.claude-profile -> work

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

## `claude-best`

Names the signed-in account with the most headroom.

```
  -> work         5% used  (5h 5%, 7d 2%)
     client      32% used  (5h 32%, 7d 17%)
```

A profile is judged by its **tightest** limit, not its average - an account at
1% for the next five hours but 95% through its week is nearly out, and is
ranked accordingly. Accounts that are locked out or not signed in are skipped.

| Flag | Effect |
|---|---|
| `-q`, `--quiet` | print just the name, for scripting |
| `--cached` | skip the live fetch and use cached figures |

Fetches live by default, so it reflects reality rather than a stale snapshot.

---

## `claude-auto`

Launch Claude on whichever account has the most headroom, without choosing
yourself.

```sh
claude-auto                       # interactive session on the best account
claude-auto -p "explain this bug"
```

It resolves `claude-best --quiet`, reports the choice on stderr, then runs
`claude` under that profile via `claude-profile-exec` - so your shell's own
profile is unchanged.

!!! tip "When to use which"
    Use `claude-profile` when the account matters (client work, a specific
    subscription). Use `claude-auto` when it does not and you just want
    capacity.

---

## `claude-prune`

Delete old conversation transcripts. **Dry run by default.**

```sh
claude-prune                      # show what is older than 90 days
claude-prune -o 30                # ...older than 30 days
claude-prune -o 90 --yes          # actually delete
```

```
╭────────┬─────────┬──────────────────────────────────────┬───────────────────────────────╮
│ WHEN   │ PROFILE │ SESSION ID                           │ DIRECTORY                     │
├────────┼─────────┼──────────────────────────────────────┼───────────────────────────────┤
│ Aug 19 │ default │ a6c22511-53a7-4a10-8e16-104b79f2dc17 │ ~/projects/<project-name>/api │
╰────────┴─────────┴──────────────────────────────────────┴───────────────────────────────╯

3 session(s) older than 90 days, 2.3MB  (90 newer session(s) untouched)
dry run - nothing deleted. pass --yes to delete.
```

| Flag | Effect |
|---|---|
| `-o DAYS`, `--older-than DAYS` | age threshold (default 90) |
| `-p NAME`, `--profile NAME` | just one profile (default: all) |
| `-n N`, `--limit N` | rows to list, `0` for all (default 20) |
| `-y`, `--yes` | actually delete |
| `--plain` | no borders |

It reports how much space would be freed and how many newer sessions it is
leaving alone, so you can see the blast radius before committing.

!!! danger "Deleted transcripts are gone"
    There is no undo, and `claude --resume` cannot reach a deleted session.
    Check the dry run first, and [hand off](guides/handoff.md) anything worth
    keeping.

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

## `claude-profiles statusline`

Inside a Claude Code session the shell prompt is gone, so the profile indicator
is not visible. This renders a status line for Claude Code's own `statusLine`
setting instead.

```
work │ you@company.com │ ⎇ main │ ctx 52%/1000k │ 5h 2% │ 7d 3% │ $12.40
```

### Enabling it

```sh
claude-profiles statusline --install                  # the active profile
claude-profiles statusline --install-all              # every profile
claude-profiles statusline --install-all --show profile,limits   # pick the segments
```

That writes the setting into each profile's `settings.json`, backing up any
existing file alongside. Settings are per-profile, which is why `--install-all`
exists. An existing status line from somewhere else is left alone unless you
pass `--force`.

Start a new Claude Code session to see it - the setting is read at launch.

<details>
<summary>Or configure it by hand</summary>

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 \"$HOME/.claude-tools/bin/claude-profiles.py\" statusline --show profile,account,limits",
    "padding": 0
  }
}
```
</details>

### Segments

`--show` takes a comma-separated list, rendered in the order you give:

| Segment | Shows |
|---|---|
| `profile` | the active profile - dim on `default`, magenta otherwise |
| `account` | the signed-in email |
| `model` | model name, plus effort level when it is not the default |
| `dir` | the current directory's basename |
| `branch` | the git branch |
| `context` | context window used, colour-coded |
| `limits` | 5-hour and 7-day usage, each its own segment |
| `cost` | what this session's tokens would cost at API rates |
| `lines` | lines added and removed this session |
| `version` | the Claude Code version |
| `session` | the session name |

Percentages are green below 75%, amber from 75%, red from 90% - the same scale
`claude-profiles` uses.

!!! note "`cost` is not a bill"
    It is `total_cost_usd` from the payload: what this session's tokens would
    cost at pay-as-you-go API rates. On a subscription you are not charged it -
    treat it as a sense of how heavy the session is. Leave the segment out if
    that number is more distracting than useful.

!!! note "These figures come from Claude Code, not the cache"
    Claude Code passes current rate limits and context usage to the status line
    on every render, so `limits` here is live without any network call of its
    own. If a payload ever lacks them, it falls back to the cached snapshot.

Check for and pull a newer version. Covered in full on the
[Updating](updating.md) page.

```sh
claude-update --check    # what is installed, and what is available
claude-update            # pull it
```

| Flag | Effect |
|---|---|
| `-c`, `--check` | report only, change nothing |

It refuses to run over uncommitted local edits, uses `git pull --ff-only`, and
tells you whether the change needs a shell restart.

---

## `claude-update`

Check for and pull a newer version. Covered in full on the
[Updating](updating.md) page.

```sh
claude-update --check    # what is installed, and what is available
claude-update            # pull it
```

| Flag | Effect |
|---|---|
| `-c`, `--check` | report only, change nothing |

It refuses to run over uncommitted local edits, uses `git pull --ff-only`, and
tells you whether the change needs a shell restart - changes under `bin/` take
effect immediately, changes under `shell/` do not.

---

## `claude-profiles.py path NAME`

Print a profile's config directory. Useful in scripts.

```sh
CLAUDE_CONFIG_DIR=$(claude-profiles.py path work) claude -p "summarise this repo"
```

That form runs a single command under a profile without switching your shell.
