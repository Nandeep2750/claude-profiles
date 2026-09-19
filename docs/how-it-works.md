# How it works

Nothing here patches or wraps Claude Code. It sets one environment variable that
Claude Code already reads, and copies transcript files that Claude Code already
understands. Remove this tooling and `claude` keeps working unchanged.

## The mechanism

Claude Code reads `CLAUDE_CONFIG_DIR` to decide where its configuration lives.
Crucially, it also derives the *credential slot* from that path. In the shipped
binary:

```js
function serviceName(suffix = "") {
  const isDefault = !process.env.CLAUDE_CONFIG_DIR;
  const hash = isDefault ? "" : "-" + sha256(configDir).slice(0, 8);
  return `Claude Code${OAUTH_FILE_SUFFIX}${suffix}${hash}`;
}
```

So each distinct `CLAUDE_CONFIG_DIR` gets its own credential entry. Signing into
one profile cannot disturb another - they are different storage keys, not a
shared slot being overwritten.

`claude-profile NAME` does one meaningful thing:

```sh
export CLAUDE_CONFIG_DIR="$CLAUDE_PROFILE_HOME/NAME"
```

Everything else is convenience on top of that.

## Where credentials live

| Platform | Storage |
|---|---|
| macOS | Keychain, service `Claude Code-credentials-<sha256(dir)[:8]>` |
| Linux, WSL, Windows | `<profile dir>/.credentials.json`, mode 600 |

The `default` profile is the unhashed original: Keychain service
`Claude Code-credentials`, or `~/.claude/.credentials.json`.

`claude-profiles` reports `AUTH ok` if either backend has an entry, so the same
command works correctly on every platform.

**Consequence:** on macOS the Keychain entry is keyed to the profile's absolute
path. Moving or renaming a profile directory orphans its credentials and forces
a re-login. Credentials also never sync between machines - run `/login` once per
profile per machine.

## What a profile contains

Setting `CLAUDE_CONFIG_DIR` relocates everything, not just the login:

```
~/.claude-profiles/work/
  .claude.json          account, per-project trust, MCP servers, last session ids
  .credentials.json     OAuth tokens (non-macOS)
  settings.json         user settings for this profile
  projects/             conversation transcripts
  sessions/             runtime session state
  plugins/  cache/  backups/
```

So profiles do not share MCP servers, permissions or settings - see
[What's shared, what isn't](isolation.md) for the full picture, including the
one exception (files inside a project folder). To copy settings across:

```sh
cp ~/.claude/settings.json ~/.claude-profiles/work/
```

Never copy `.credentials.json` between profiles - it belongs to one account.

## Where conversations live

```
<profile>/projects/<encoded-cwd>/<session-id>.jsonl
```

The directory name encodes the working directory by replacing `/` and `.` with
`-`:

```
~/projects/<project-name>  ->  -Users-you-projects-<project-name>
```

Each `.jsonl` line is one event: user messages, assistant messages, tool calls,
file snapshots. Every line also records its own `cwd`, which is what
`claude-sessions` and `claude-handoff` match on - more reliable than
reconstructing the encoded directory name.

`claude --resume` only looks inside the active profile's `projects/`. That is
precisely why handoff is needed: the other account is not hiding the
conversation, it genuinely cannot see the file.

## What handoff actually does

```
~/.claude/projects/<encoded-dir>/<session-id>.jsonl
        |  copy, preserving the encoded directory name
        v
~/.claude-profiles/work/projects/<encoded-dir>/<session-id>.jsonl
```

Only the profile root changes. The encoded directory segment is identical, and
the file is byte-for-byte the same, so every `cwd` inside it still points at the
original project. Resuming drops you into the same directory, same files, same
git branch - only the billing account differs.

Resuming re-sends the whole conversation to the new account, so its first turn
is a cold prompt cache and costs more than an ordinary continuation.

## Auto-switching on `cd`

A shell hook (`chpwd` in zsh, `PROMPT_COMMAND` in bash) walks up from the
current directory looking for a `.claude-profile` file, and switches to the name
inside it. No match means `default`.

The walk is plain shell with an early-exit guard when the directory has not
changed, so it costs nothing per prompt. It deliberately does not shell out to
Python, which would add ~50ms to every `cd`.

## Layout

```
~/.claude-tools/                 the repo - logic only, safe to commit
  bin/claude-profiles.py         status / sessions / handoff / path
  shell/claude-profiles.zsh      zsh functions, cd hook, completion
  shell/claude-profiles.bash     bash equivalent
  shell/ClaudeProfiles.psm1      PowerShell module
  install.sh  install.ps1
  docs/

~/.claude-profiles/              account data - machine-local, never committed
  work/  client/  ...            one directory per account
```

The shell layers locate the Python core relative to their own file
(`${(%):-%x}` in zsh, `$BASH_SOURCE` in bash, `$PSScriptRoot` in PowerShell), so
the clone path is not hardcoded anywhere.

## Version sensitivity

`claude-profile`, `claude-profiles` and `claude-handoff` rely on documented,
stable behaviour: an environment variable and the on-disk transcript location.

`claude-sessions` additionally parses transcript contents to build summaries.
That format is internal to Claude Code and could change in a future release. If
summaries ever come out blank, that parsing is the thing to look at -
`scan()` in [`bin/claude-profiles.py`](https://github.com/Nandeep2750/claude-profiles/blob/main/bin/claude-profiles.py).
