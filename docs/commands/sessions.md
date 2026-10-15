# Sessions

Finding past conversations, moving one to another account, and deleting the
ones you are done with.

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

A session that exists in more than one profile - because it was handed off - is
marked, so you can see at a glance where to resume it:

```
 1  work      0m ago   145  eb82f424 *   refactor the auth middleware…
 2  personal  6m ago   139  eb82f424 ·   refactor the auth middleware…
```

`*` is the copy with the most turns, which is the one you continued on. `·` is
behind. On a tie the more recently used one wins.

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
| `-f`, `--force` | overwrite a target copy that is ahead or has diverged |
| `--move` | retire the source copy after handing off (the default) |
| `--copy` | leave the source copy in place |

On success it prints the resume command:

```
moved session 0a9014e8-8806-43cf-98fd-28fad1353923
  from: default   to: work
  dir : ~/projects/<project-name>/api
  side files: 24 copied
  default's copy retired as 0a9014e8-8806-43cf-98fd-28fad1353923.jsonl.bak - undo by renaming it back

  claude-profile work && claude --resume 0a9014e8-8806-43cf-98fd-28fad1353923
```

**Guards.** An ambiguous prefix lists the matches instead of guessing. Handing
off to the same profile, or to one that does not exist, is refused with a
message rather than silently doing nothing.

### Move or copy

By default handoff **moves** the session. The transcript is copied, the copy is
verified byte for byte, and only then is the source renamed to
`<session-id>.jsonl.bak`. A renamed file is invisible to `claude-sessions` and
to `claude --resume`, so there is one live copy and no question of which to
resume - and undoing a move is a rename.

| | `--move` (default) | `--copy` |
|---|---|---|
| Target | gets the session | gets the session |
| Source | transcript renamed to `.bak`, side files removed | left in place |
| Where to resume | the target, unambiguously | either - `claude-sessions` marks the leader |
| If the copy fails to verify | source untouched | source untouched |

Reach for `--copy` to try something on another account without committing to it.
Set `CLAUDE_HANDOFF_COPY=1` to make it your default; `--move` overrides that for
one command.

!!! note "Existing installs"
    Before 2.0.0 handoff only ever copied. Running `claude-update` changes the
    default to move. Pass `--copy` or set `CLAUDE_HANDOFF_COPY=1` to keep the
    old behaviour.

### When the target already has the session

Handing the same session back and forth is normal: you move it to `personal`
when `work` runs out, then back to `work` once the limit resets. So the target
often already has a copy, and overwriting the wrong one would lose turns.

What happens depends on which copy is further along:

| Target copy | Result |
|---|---|
| Not there | copied |
| Identical | nothing to do, says so |
| Fewer turns | updated, reports `3 turns -> 7` |
| **More turns** | **refused** - that copy has work the source does not |
| Same turns, different contents | **refused** - they were continued separately |

A refusal tells you both turn counts, so you can see which copy to resume:

```
work already has this session and it would be overwritten
  work: 7 turns   personal: 4 turns  - the copy in work is further along
  resume it there instead, or pass --force to overwrite (a .bak is kept)
```

`--force` overwrites anyway and writes the previous contents to
`<session-id>.jsonl.bak` first, so nothing is unrecoverable.

### The session's own side files

A long conversation is not only its transcript. Claude Code spills big tool
results, subagent transcripts and workflow journals into a directory named
after the session, next to it:

```
~/.claude-profiles/<profile>/projects/<encoded-dir>/
  <session-id>.jsonl      the conversation
  <session-id>/           its side files - tool results, subagents, workflows
  memory/                 facts about the project, shared by every session here
```

Those side files belong to that one session, so handoff takes them along
without being asked. There is no flag. Memory is different - it is shared by
every session in the project, so moving it is your decision and needs
`--with-memory`.

```
moved session 0a9014e8-…
  from: default   to: work
  side files: 24 copied
```

Merging follows the same no-overwrite rule as memory:

| Situation | What happens |
|---|---|
| File only in the source | copied |
| File only in the target | left alone |
| Same file, identical | nothing to do |
| Same name, different contents | **the target's is kept**, and a move leaves the source directory in place |

That last row is the safe default: rather than pick a winner, the command keeps
both sides and says so.

```
moved session 0a9014e8-…
  side files: 23 copied, 1 kept the target's
  default's side files stayed - some of them differ in the target
```

A `--copy` handoff copies the side files and leaves the originals alone, same as
it does with the transcript.

!!! note "Upgrading from 2.0"
    Handoffs made before 2.1.0 left the side directory behind in the source
    profile. A resumed session still works - Claude Code refetches what it
    needs - but old tool results and subagent transcripts stay in the old
    account. `claude-profiles doctor` reports any that are stranded.

### Carrying the project's memory across

Claude Code saves memory per profile **and** per project:

```
~/.claude-profiles/<profile>/projects/<encoded-dir>/
  <session-id>.jsonl      the conversation - moved
  <session-id>/           the session's side files - moved
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
moved session a3f81c2e-…
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

## `claude-clear [PATH]`

Delete the conversations recorded for one project directory, across every
profile. Use it when a project is finished, or when you want a clean slate for
it without touching anything else.

```sh
claude-clear                            # the current directory
claude-clear ~/projects/<project-name>  # a specific project
```

!!! tip "Look before you delete"
    Add `-n` to any of these. It prints the same list and the exact files it
    would remove, and deletes nothing.

    ```sh
    claude-clear ~/projects/<project-name> -n --all
    ```

It checks the path exists first, then lists what it found and asks which to
delete:

```
3 session(s) for ~/projects/<project-name>  41.2MB across 2 profile(s)

╭───┬─────────┬────────┬───────┬────────┬──────────────────────────────────────┬──────────────────────────╮
│ # │ PROFILE │ WHEN   │ TURNS │   SIZE │ SESSION ID                           │ SUMMARY                  │
├───┼─────────┼────────┼───────┼────────┼──────────────────────────────────────┼──────────────────────────┤
│ 1 │ work    │ 2d ago │   191 │ 38.4MB │ c9f6d2ae-80e4-456d-a6c9-2b6c562c6313 │ set up the staging box…  │
│ 2 │ default │ Oct 03 │    17 │  2.6MB │ 6f2c1864-f20c-4eba-b105-dbf8f4814ed9 │ fix the failing test…    │
│ 3 │ work    │ Oct 03 │     1 │  212KB │ 2ac384e3-453d-45bb-9dd8-fa293c0b58fe │ ok                       │
╰───┴─────────┴────────┴───────┴────────┴──────────────────────────────────────┴──────────────────────────╯

which to delete?
  2        one
  1,3,5-7  several
  all      every session listed
  enter    cancel
>
```

Pick numbers and it shows exactly which files will go, then asks once more:

```
about to delete 2 session(s), 38.6MB:
  c9f6d2ae-80e4-456d-a6c9-2b6c562c6313  work, 191 turns, 38.4MB
      ~/.claude-profiles/work/projects/-Users-you-projects-<project-name>/c9f6d2ae-….jsonl
      ~/.claude-profiles/work/projects/-Users-you-projects-<project-name>/c9f6d2ae-…  (side files)
  6f2c1864-f20c-4eba-b105-dbf8f4814ed9  default, 17 turns, 2.6MB
      ~/.claude/projects/-Users-you-projects-<project-name>/6f2c1864-….jsonl

this cannot be undone. type y to delete:
```

| Flag | Effect |
|---|---|
| `PATH` | project directory (default: the current one) |
| `-p NAME`, `--profile NAME` | just one profile (default: all of them) |
| `-r`, `--under` | also sessions started in subdirectories of `PATH` |
| `-s ID`, `--session ID` | delete this id or prefix instead of prompting. Repeatable |
| `-a`, `--all` | select every session listed |
| `-n`, `--dry-run` | show what would go, delete nothing |
| `-y`, `--yes` | skip the confirmation |
| `--traces` | instead, sweep files left by sessions that are already deleted |
| `--plain` | no borders |

### What it looks at, and what it deletes

Sessions are matched on the working directory **recorded inside** each
transcript, not on the folder name, so a session handed between profiles is
still found. Symlinks are resolved, so `/tmp` and `/private/tmp` match.

Deleting a session removes everything that belongs to it. The conversation is
only part of that: Claude Code keys several folders beside `projects/` by
session id, and some of them hold real content.

| Removed | What it held |
|---|---|
| `projects/<dir>/<session-id>.jsonl` | the conversation |
| `projects/<dir>/<session-id>.jsonl.bak` | a copy left by an earlier handoff |
| `projects/<dir>/<session-id>/` | its tool results and subagent transcripts |
| `file-history/<session-id>/` | **copies of every file that session edited**, version by version |
| `jobs/<short-id>/` | a background job's state and timeline |
| `session-env/<session-id>/` | its environment |
| `tasks/<session-id>/` | its task state |
| anything else named `<session-id>` or `<session-id>.*` | plugin notes and the like |

Only exact names count. A folder that merely contains the id, and another
session's files, are never touched.

| Kept | Why |
|---|---|
| `memory/` | shared by every session in the project, not owned by one conversation |
| sessions for other directories | out of scope |
| sessions in subdirectories | unless you pass `-r` |

`file-history/` is the one that matters most. It holds readable copies of your
source files as that session changed them, so deleting the transcript alone
leaves the content behind. Delete the `memory/` folder yourself if you want
that gone too.

!!! warning "Deleting is not erasing"
    These files are unlinked, not overwritten, so the blocks survive until the
    disk reuses them. Your backups keep their own copies regardless. If a
    session saw a password or a token, rotate it - do not rely on deleting the
    file.

### Sweeping up after older versions

Before 2.3.0, `claude-clear` removed the transcript and its side files but not
the folders beside `projects/`. `claude-prune` never removed them either.
`claude-doctor` reports whatever is left, and one command clears it:

```sh
claude-clear --traces -n     # list what is left over, delete nothing
claude-clear --traces        # list, then ask before deleting
claude-clear --traces -p work
```

It only ever removes files named after a session that no longer exists in that
profile, so nothing a live session needs can be caught by it.

```
119 file(s) named after sessions that no longer exist, 7.2MB

╭─────────┬───────────────┬───────┬─────────┬───────────────────────────────╮
│ PROFILE │ WHERE         │ FILES │    SIZE │ WHAT IT HELD                  │
├─────────┼───────────────┼───────┼─────────┼───────────────────────────────┤
│ default │ file-history  │     4 │   2.1MB │ copies of the files it edited │
│ default │ jobs          │     2 │   2.3KB │ a background job's state      │
│ work    │ session-env   │    29 │      0B │ its environment               │
╰─────────┴───────────────┴───────┴─────────┴───────────────────────────────╯
```

### Without a prompt

For scripts, choose up front. Without a selection and without a terminal it
refuses rather than guessing:

```sh
claude-clear ~/projects/<project-name> -s a3f81c2e -y   # one session
claude-clear ~/projects/<project-name> --all -y         # all of them
claude-clear ~/projects/<project-name> --all -n         # just show the plan
```

### Recipes

| Goal | Command |
|---|---|
| See what is there, change nothing | `claude-clear ~/projects/<project-name> -n --all` |
| Clear the project you are standing in | `claude-clear` |
| Include sessions from its subfolders | `claude-clear ~/projects/<project-name> -r` |
| Only one account's copies | `claude-clear ~/projects/<project-name> -p work` |
| Drop one session by its id prefix | `claude-clear ~/projects/<project-name> -s a3f81c2e -y` |
| Wipe the project, no prompt | `claude-clear ~/projects/<project-name> --all -y` |
| Clean up after older versions | `claude-clear --traces -n` |
| Easier to read in a narrow window | add `--plain` |

Flags combine, so `-r -p work -n` previews everything `work` recorded in that
project and below it.

!!! danger "There is no undo"
    Unlike a handoff, this deletes. `claude --resume` cannot reach a cleared
    session and no `.bak` is kept. Run it with `-n` first, and
    [hand off](../guides/handoff.md) anything worth keeping.

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

`claude-prune` works by age across every project. To clear one project
regardless of age, use [`claude-clear`](#claude-clear-path).

!!! danger "Deleted transcripts are gone"
    There is no undo, and `claude --resume` cannot reach a deleted session.
    Check the dry run first, and [hand off](../guides/handoff.md) anything worth
    keeping.

---
