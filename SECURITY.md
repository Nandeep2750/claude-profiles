# Security

## What this tool touches

`claude-profiles` handles Claude Code credentials. Specifically it:

- **Reads** OAuth tokens from the macOS Keychain, or from
  `<profile>/.credentials.json` on Linux and Windows, in two places:
  `--live` and `claude-best`, to authenticate a usage lookup.
- **Sends** those tokens to `https://api.anthropic.com` only - the same host
  Claude Code already authenticates against. Nothing is sent anywhere else.
- **Deletes** a Keychain entry when you remove the profile it belongs to.

It never writes tokens to disk, never logs them, never copies them between
profiles, and has no telemetry or analytics of any kind.

## Reporting a vulnerability

Please report privately through
[GitHub Security Advisories](https://github.com/Nandeep2750/claude-profiles/security/advisories/new)
rather than opening a public issue.

Include what you did, what happened, and the version from
`claude-profiles --version`. You can expect an initial response within a few
days.

## Things worth knowing

- **Profile names are validated** before being used as paths, because commands
  such as `claude-profile-remove` delete what a name resolves to. Names are
  restricted to letters, digits, `.`, `-` and `_`, and cannot traverse out of
  `CLAUDE_PROFILE_HOME`.
- **On Linux and Windows, credentials sit in a plaintext file** - that is how
  Claude Code stores them, not a choice made here. `claude-doctor` warns if that
  file is readable by other users.
- **`~/.claude-profiles` must never be committed** to a repository. It holds
  credentials and full conversation transcripts. The tooling lives in a separate
  directory precisely so this cannot happen by accident, and `claude-doctor`
  fails if it finds a `.git` directory there.
- **`--live` calls an endpoint that is internal to Claude Code.** It is not a
  documented public API and may change without notice.
