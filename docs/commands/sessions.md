# Sessions

Finding past conversations, moving one to another account, and clearing out old
ones.

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

---

## `claude-handoff TARGET [SESSION]`

Copy a conversation into another profile so that account can resume it. See the
[guide](../guides/handoff.md) for what this is
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
| `-m`, `--with-memory` | also merge this project's saved memory into the target |
| `--force-memory` | replace the target's memory instead of merging |
| `-n`, `--dry-run` | show what would happen, change nothing |

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

### Carrying the project's memory across

Claude Code saves memory per profile **and** per project:

```
~/.claude-profiles/<profile>/projects/<encoded-dir>/
  <session-id>.jsonl      the conversation - this is what handoff copies
  memory/                 saved facts about the project - a sibling, left alone
```

A plain handoff moves the conversation, not the memory. The conversation itself
carries everything that was said, so you can keep working - but the distilled
facts Claude normally reads at the start of a session stay behind.

```sh
claude-handoff work --with-memory
```

That merges them:

| Situation | What happens |
|---|---|
| File only in the source | copied |
| File only in the target | left alone |
| Same file, identical | nothing to do |
| Same name, different contents | **both kept** - the incoming one saved as `<name>.from-<source>.md` |
| `MEMORY.md` | the two indexes are combined, keeping the target's order |

Memory is one file per fact with a unique name, so merging is a set union
rather than an edit of prose. Nothing is overwritten and nothing is lost.

```
handed off session a3f81c2e-…
  from: work   to: personal
  memory: 2 copied, 1 already there, 1 kept side by side
```

Look before you leap:

```sh
claude-handoff work --with-memory --dry-run
```

```
dry run - nothing will be written
would hand off a3f81c2e-…  work -> personal
  copy     no-em-dashes.md
  same     show-drafts.md
  differs  api-conventions.md -> kept as api-conventions.from-work.md
```

`--force-memory` replaces the target's memory for that project outright. Rarely
what you want, and it does discard whatever the target had learned.

!!! tip "The better fix for most facts"
    Anything true about the **project** regardless of which account you use
    belongs in `CLAUDE.md` in the repository. Every profile reads it, it
    survives handoffs, and it is version-controlled. Profile memory then holds
    only the account-specific things, and losing those on a handoff is correct
    rather than a gap.

---

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
leaving alone, so you can see the what will be deleted before committing.

!!! danger "Deleted transcripts are gone"
    There is no undo, and `claude --resume` cannot reach a deleted session.
    Check the dry run first, and [hand off](../guides/handoff.md) anything worth
    keeping.

---
