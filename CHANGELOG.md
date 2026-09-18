# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[1.0.0]: https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.0.0
