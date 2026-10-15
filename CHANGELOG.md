# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-10-15

### Fixed

- **Deleting a session left its content on disk.** Claude Code keys several
  folders beside `projects/` by session id, and `claude-clear` only swept the
  transcript and its side files. The worst of them was
  `file-history/<session-id>/`, which holds readable copies of every file that
  session edited, version by version; `jobs/<short-id>/` held a background
  job's state and timeline. Clearing a session now removes anything in the
  profile named exactly `<session-id>` or `<session-id>.*`, plus the
  8-character prefix `jobs/` uses. `memory/` is still kept, and a name that
  merely contains the id is never touched. The short-prefix rule applies to
  `jobs/` alone, and is skipped when two sessions share those eight
  characters, so clearing some of a project's sessions cannot reach the ones
  you kept.
- The confirmation list now says what each file held
  (`copies of the files it edited`) instead of labelling every directory
  `side files`.

### Added

- **`claude-clear --traces`** sweeps files left behind by sessions that are
  already gone - from `claude-prune`, which never removed them, or from
  `claude-clear` before this release. It only removes files named after a
  session the profile no longer has, lists them grouped by profile and folder
  first, and asks before deleting.
- `claude-doctor` reports those leftovers, with the command to clear them.

### Changed

- The documentation now states plainly that deleting unlinks rather than
  erases, and that a secret a session saw should be rotated rather than
  deleted.

## [2.2.0] - 2026-10-15

### Added

- **`claude-clear [PATH]`** - delete the conversations recorded for one project
  directory, across every profile. It checks the path exists, lists what it
  found with a number per row, and asks which to delete (`2`, `1,3,5-7` or
  `all`), then shows the exact files and asks once more. `-s ID` / `--all` with
  `-y` choose without a prompt, `-n` shows the plan, `-r` includes sessions
  started in subdirectories.
  - Deleting a session removes its transcript, any `.jsonl.bak` beside it and
    its `<session-id>/` side files. The project's `memory/` is deliberately
    kept: it belongs to the project, not to one conversation.
  - Sessions are matched on the working directory recorded inside each
    transcript, with symlinks resolved, so a handed-off session is still found.
  - Refuses to act without a selection when there is no terminal, rather than
    guessing.

### Fixed

- **Windows was missing commands the docs promised.** The PowerShell module had
  no `path` or `statusline`, and `claude-profiles` sent every argument to
  `status` instead of dispatching subcommands, so `claude-profiles clear` and
  `claude-profiles statusline` did the wrong thing. It now dispatches the same
  list bash and zsh do, and gained `Get-ClaudeProfilePath`,
  `Set-ClaudeStatusLine` and `Start-ClaudeAuto` (`claude-auto`).
- **`claude-profile-exec NAME CMD` with no arguments ran the wrong thing on
  Windows.** PowerShell counts `1..0` downwards, so a one-element command list
  was passed as its own argument.
- `claude-path` and `claude-statusline` now exist in all three shells, not just
  PowerShell. A test checks every documented `claude-*` name against all three
  layers.
- `claude-clear` matches a project path the way the filesystem does, so a path
  typed in a different case finds its sessions on Windows and macOS without
  ever merging two genuinely different directories on a case-sensitive one.
- Shell-layer tests now parse each layer before using it. A syntax error part
  way down a file still leaves the functions above it defined, so the old tests
  could pass while `source` was failing - which is how a broken zsh completion
  reached CI.

- **`claude-prune` could delete a live session's side files.** It listed every
  `.jsonl` under `projects/`, which includes the subagent transcripts and
  workflow journals Claude Code writes inside `<session-id>/`. On real data that
  made it offer 504 "sessions" where only 106 existed, and `--yes` would have
  deleted the side files of sessions that were nowhere near the age cutoff.
  Session listing is now limited to the transcripts themselves, which fixes
  `prune`, `sessions` and `handoff` alike.

## [2.1.0] - 2026-10-13

### Added

- **`claude-handoff` now takes the session's side files with it.** Claude Code
  spills large tool results, subagent transcripts and workflow journals into a
  `<session-id>/` directory beside the transcript. Handoff moved the transcript
  and left that directory behind, so a resumed session lost them. They now
  travel with the transcript, no flag needed - they belong to that one session,
  unlike memory, which is shared by the whole project and still needs
  `--with-memory`.
  - Merging never overwrites: a file the target already has with different
    contents is kept, and a move then leaves the source directory in place and
    says so.
  - `--copy` copies the side files and leaves the originals alone.
- `claude-doctor` reports stranded side-file directories - ones whose
  transcript is no longer in that profile, left behind by a handoff made before
  this release.

### Changed

- Transcript comparisons read in 64 KiB chunks instead of loading both files
  into memory. A 275 MB transcript no longer needs 550 MB to verify.

## [2.0.0] - 2026-10-13

### Changed - breaking

- **`claude-handoff` now moves the session instead of copying it.** The
  transcript is copied to the target, the copy is verified byte for byte, and
  only then is the source renamed to `<session-id>.jsonl.bak`. The `.bak` is
  invisible to `claude-sessions` and `claude --resume`, so a session lives in
  exactly one profile and there is no question of which copy to resume. Undoing
  a move is renaming the `.bak` back.

  Previously handing off left a live copy in both profiles, which meant you had
  to work out afterwards which one had the later work.

  **If you want the old behaviour**, pass `--copy`, or set
  `CLAUDE_HANDOFF_COPY=1` to make it your default. `--move` overrides the
  variable for a single command.

  The safety properties are unchanged: a copy that fails to verify leaves the
  source untouched, and the overwrite guard still refuses a target that is ahead
  or has diverged - a refused move retires nothing.

### Added

- `--move`, `--copy` on `claude-handoff`, and `CLAUDE_HANDOFF_COPY`.
- The output says `moved session` and names the `.bak`, so it is clear what
  happened to the source.
- `--dry-run` reports `would move` and which `.bak` it would leave.

## [1.10.0] - 2026-10-12

### Fixed

- **`claude-handoff` could silently destroy work.** It copied the transcript
  over whatever was already in the target, with no check. Handing a session
  from `x` to `y` and later back to `x`, after both had been continued
  separately, overwrote the longer copy and reported success. A seven-turn
  conversation became a four-turn one with no warning.

  It now compares the two copies. A target with fewer turns is updated, an
  identical one is left alone, and a target that is further along or has
  diverged is **refused** with both turn counts shown. `--force` overwrites and
  keeps the previous contents as `<session-id>.jsonl.bak`.

  Every other destructive path in this tool already guarded itself. Handoff did
  not, because it was written assuming the target never had that file.

### Added

- `claude-sessions` marks a session that exists in more than one profile: `*`
  on the copy with the most turns, `·` on the ones behind. After a handoff both
  profiles hold a copy, and nothing previously said which to resume.

## [1.9.0] - 2026-09-21

### Added

- **`claude-handoff --with-memory`** carries a project's saved memory across
  with the conversation. Claude Code stores memory per profile and per project,
  so a plain handoff left it behind - the conversation continued fine, but the
  facts Claude reads at the start of a session did not travel.

  It merges rather than overwrites: new facts are copied, existing ones left
  alone, and a fact that differs on both sides is kept twice, the incoming one
  as `<name>.from-<source>.md`, with both listed in `MEMORY.md`. Memory is one
  file per fact, so this is a set union rather than an edit of prose.

- `--dry-run` on `claude-handoff`, showing exactly what would be copied, kept
  and flagged before anything is written.
- `--force-memory` to replace the target's memory outright, for when that is
  genuinely what you want.
- A plain handoff now says when the project has memory that is being left
  behind, rather than staying silent about it.

### Fixed

- `claude-profile --help` reported "invalid profile name: --help", and
  `claude-auto --help` launched Claude instead of explaining itself. Both are
  shell-only functions with no core subcommand behind them, so neither had ever
  had help. All twelve commands now answer `--help`.

## [1.8.0] - 2026-09-21

### Added

- An animated demo on the README, the documentation home and the handoff
  guide. It runs the real workflow: `claude-profiles` shows `work` 91% through
  its weekly limit, `claude-best` picks the account with room, and
  `claude-handoff` moves the conversation there.

  The terminal output in it is genuine - generated by running the tool against
  dummy profiles - rather than typed out by hand.

## [1.7.4] - 2026-09-21

### Added

- A screenshot on the README, the documentation home, the usage reference and
  the handoff guide. It shows two accounts with their limits side by side and
  a conversation being moved between them - the situation this tool exists for,
  which is hard to convey in prose.

## [1.7.3] - 2026-09-21

### Fixed

- **`claude-profile` and `claude-profiles` with no arguments crashed in a shell
  running `set -u`** with "$1: unbound variable" - the most basic documented
  usage. The zsh prompt setup read `$RPROMPT` unguarded and failed the same
  way. Every parameter reference in both shell layers is now guarded.

### Added

- The shell and end-to-end tests now clear every `CLAUDE_*` setting before
  running. They inherited the developer's own environment, so setting
  `CLAUDE_DEFAULT_PROFILE` locally made two tests fail for a reason that had
  nothing to do with the code.
- **`tests/test_docs_commands.sh`** extracts every command shown in the
  documentation and runs it in a throwaway `HOME`, so the docs and the tool
  cannot drift apart. It also checks the functions survive `set -u`. In CI for
  bash and zsh.

## [1.7.2] - 2026-09-21

### Fixed

- **The Commands page redirected to itself.** When `commands.md` moved to
  `commands/index.md` it kept serving the same `/commands/` URL, so the
  redirect added for the restructure pointed the page at itself and replaced
  the real content with a redirect stub. Removed - only genuinely moved pages
  need an entry.

## [1.7.1] - 2026-09-19

### Fixed

- **The prompt indicator now stays quiet on your configured default**, not just
  on `default`. Anyone using `CLAUDE_DEFAULT_PROFILE` saw the indicator on every
  prompt, which defeats its purpose: it is meant to speak up only when you are
  somewhere unusual.

## [1.7.0] - 2026-09-19

### Added

- **`claude-doctor --check-upstream`** verifies the two Claude Code internals
  this tool depends on - the transcript format and the usage endpoint - against
  your own data. It reads your newest transcript and confirms the fields are
  still where `claude-sessions` looks for them, then calls the endpoint once and
  confirms the reply still carries both limits.

  A transient problem (expired token, rate limit, no transcripts yet) warns
  rather than fails, so it does not cry wolf.

  This cannot live in CI: CI has no Claude credentials and its transcripts are
  synthetic fixtures, so it would only ever test the fixtures. The check has to
  run where the real data is.

## [1.6.0] - 2026-09-19

### Changed

- **The documentation site is restructured.** Seven top-level tabs replace one
  long sidebar, and the 631-line command reference is split into an overview
  plus six grouped pages - switching profiles, usage and limits, sessions,
  managing profiles, the status line, and health and updates. No page is now
  longer than 184 lines.
- Guides and How it works each gained a landing page, so a section is something
  you can arrive at rather than only pass through.
- Settings and Updating left the "Reference" grouping. Settings is a top-level
  tab; Updating sits with How it works.
- A plain-English pass across every page: hard words replaced, long sentences
  split, and the jargon that had crept in removed.
- Links published before this restructure still work: `/commands/`,
  `/how-it-works/`, `/isolation/` and `/updating/` redirect to their new
  homes, so earlier release notes and any bookmarks do not break.

## [1.5.3] - 2026-09-19

### Fixed

- **Reload advice was POSIX-only.** `claude-update` and six places in the
  documentation told every user to run `exec $SHELL -l`, which is not a
  PowerShell command - leaving Windows users with no valid instruction. The
  message is now platform-aware, and the docs give the command per platform.
- **Restarting the shell was only ever shown inside a sample output block** on
  the Updating page, so it read as illustration rather than a step. It is now
  its own section, with tabs for macOS/Linux/WSL and Windows, and a note that
  only already-open terminals need it.

## [1.5.2] - 2026-09-19

### Fixed

- **`claude-profiles statusline` was unreachable through the shell wrapper.**
  The wrapper matches a hardcoded list of subcommands and `statusline` was
  never added, so it fell through to `status` and failed with "unrecognized
  arguments". The shell tests now derive that list from the core, so a new
  subcommand cannot silently go missing again.

- `claude-doctor` now warns when `CLAUDE_CONFIG_DIR` points outside
  `CLAUDE_PROFILE_HOME`, where this tool cannot see it as a profile and its
  messages become confusing.

### Added

- **`tests/test_e2e.sh`** - every user-facing command run for real through the
  shell wrappers, asserting on what it prints, with all destructive operations
  confined to a throwaway `HOME`. 59 checks per shell, in CI for bash and zsh.
  The `statusline` bug passed both existing test layers, which only proved the
  core worked and the layer loaded.

### Changed

- Documentation: the Settings page now explains how a profile is chosen -
  nearest `.claude-profile` marker, then `CLAUDE_DEFAULT_PROFILE`, then
  `default` - and how to mark a project. Previously the fallback was described
  without ever mentioning the markers it falls back from.

## [1.5.1] - 2026-09-19

### Fixed

- **`--live` now remembers what it fetched.** It displayed fresh figures and
  discarded them, so the next plain `claude-profiles` fell back to a snapshot
  that could be many hours old. Results are written beside the profile, and
  whichever cache is newer is used. Claude Code's own `.claude.json` is still
  never written to - that file is its to manage.

## [1.5.0] - 2026-09-19

### Added

- **`claude-profiles statusline --install` / `--install-all`** write the
  `statusLine` setting into a profile's `settings.json`, so enabling the status
  line no longer means hand-editing JSON in each profile. An existing status
  line from another tool is left alone unless `--force` is passed.

### Changed

- The `cost` segment is documented as what a session's tokens would cost at API
  rates, not a charge on a subscription.
- A live release badge on the README and documentation home, so the current
  version is visible without trusting prose that can go stale.

## [1.4.0] - 2026-09-19

### Added

- **`claude-profiles statusline`** — a status line for use inside Claude Code,
  where the shell prompt is not visible. Shows the active profile, account,
  git branch, context window, rate limits and session cost, configurable with
  `--show`. Rate limits and context come from the payload Claude Code passes
  in, so they are current without an extra network call.
- `statusline --install` / `--install-all` write the setting into a profile's
  `settings.json`, so enabling it does not mean hand-editing JSON.

## [1.3.0] - 2026-09-19

### Changed

- **`--live` now says why it fell back.** A failed fetch previously showed only
  `(cached)`, which made an expired token look like the feature was broken. The
  `AS OF` column now distinguishes `token expired`, `rate limited`,
  `unreachable`, `not logged in` and `http NNN`, with a hint below the table.
- `claude-doctor` warns when a profile's access token has expired.

### Added

- `token_expiry()` reads a profile's token expiry from either credential
  backend.

### Note

Access tokens are short-lived and Claude Code refreshes them when it runs. This
tool deliberately does not refresh them: refresh tokens can rotate, and writing
one back risks desynchronising Claude Code's own credential state. Running any
session under a profile refreshes its token.

## [1.2.1] - 2026-09-18

### Security

- **Profile names are now validated before being used as paths.** A name such
  as `../Documents` resolved outside `CLAUDE_PROFILE_HOME`, so
  `claude-profile-remove ../Documents` deleted that directory. Names are now
  restricted to letters, digits, `.`, `-` and `_`, and are checked in the core
  and in all three shell layers. Regression tests cover it.

### Fixed

- `claude-best` crashed with a `TypeError` when an account reported only one of
  its two limits.
- Reset timestamps ending in `Z` were unparseable before Python 3.11 and showed
  as `-`.
- A mangled list comprehension in `claude-doctor`'s rc-file check would have
  raised `NameError`.
- `_buckets` now also finds a `limits` array at the payload's top level, not
  only nested inside `utilization`.
- Removed an unused `textwrap` import.

### Added

- `ruff` and `shellcheck` run in CI, with configuration checked in.
- `CONTRIBUTING.md`, `SECURITY.md`, issue and pull-request templates,
  `.editorconfig`, and Dependabot for actions and pip.

## [1.2.0] - 2026-09-18

### Added

- **`claude-update`** — reports the installed and latest versions, pulls the
  newer one with `git pull --ff-only`, lists what changed, and says whether the
  change needs a shell restart. Refuses to run over uncommitted local edits.
- **`claude-update --check`** — report only, change nothing.
- `--version` and `claude-doctor` now include the git description, so
  `1.2.0 (v1.2.0-3-gabc1234)` tells you exactly what you are running.

## [1.1.0] - 2026-09-18

### Added

- **`claude-sessions --grep`** — search the full text of every message, yours
  and Claude's, across any profile and directory. Matching sessions show the
  matching passage in context instead of the opening prompt.
- **`claude-best`** — names the signed-in account with the most headroom, judged
  by its tightest limit rather than an average, so an account at 1% for five
  hours but 95% for the week is not mistaken for free.
- **`claude-auto`** — launches Claude on that account without switching your
  shell.
- **`claude-prune`** — delete old transcripts, dry run by default, reporting
  what would be freed and how many newer sessions are being left alone.

## [1.0.0] - 2026-09-18

First tagged release.

### Added

- **Profiles** — `claude-profile` switches between Claude Code accounts by
  setting `CLAUDE_CONFIG_DIR`. Each profile gets its own credential slot, so
  several accounts stay signed in at once.
- **`claude-profiles`** — accounts, auth state, and usage for every profile,
  with separate 5-hour and 7-day limits and their reset clocks.
- **`claude-profiles --live`** — current usage fetched per profile in parallel,
  at no model-token cost, falling back to the cached snapshot on failure.
- **`claude-sessions`** — conversations listed readably, so you can identify one
  by what it was about rather than by a 36-character id.
- **`claude-handoff`** — copy a conversation into another profile and continue
  it there when an account hits its limit.
- **`claude-profile-remove`** — delete a profile, its history and its
  credentials, including the macOS Keychain entry that `rm -rf` leaves behind.
- **`claude-profile-clone`** — seed a new profile's settings, plugins, skills
  and agents from an existing one. Never copies credentials or history.
- **`claude-profile-exec`** — run one command under a profile without switching
  your shell.
- **`claude-doctor`** — checks the environment, shell wiring, credential file
  permissions, orphaned Keychain entries, and markers naming missing profiles.
- **Per-project profiles** — a `.claude-profile` marker selects an account on
  `cd`; the nearest one walking up wins.
- **`CLAUDE_DEFAULT_PROFILE`** — where unmarked directories fall back to.
- **`CLAUDE_PROFILE_PROMPT`** — show the active profile in your prompt.
- Tab completion for every command in zsh and bash.
- Installers for macOS, Linux, WSL, Git-Bash and Windows PowerShell.
- Documentation site built with MkDocs Material.
- 48 core tests and 33 shell tests, run on Ubuntu and macOS across Python 3.9
  and 3.13, in both bash and zsh, plus a PowerShell check on Windows.

[2.3.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v2.3.0
[2.2.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v2.2.0
[2.1.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v2.1.0
[2.0.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v2.0.0
[1.10.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.10.0
[1.9.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.9.0
[1.8.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.8.0
[1.7.4]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.7.4
[1.7.3]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.7.3
[1.7.2]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.7.2
[1.7.1]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.7.1
[1.7.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.7.0
[1.6.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.6.0
[1.5.3]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.5.3
[1.5.2]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.5.2
[1.5.1]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.5.1
[1.5.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.5.0
[1.4.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.4.0
[1.3.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.3.0
[1.2.1]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.2.1
[1.2.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.2.0
[1.1.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.1.0
[1.0.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.0.0
