# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
