<div align="center">

# claude-profiles

**Run multiple Claude Code accounts on one machine.**

Pick an account per project, and move a conversation between accounts
when one hits its usage limit.

[![CI](https://github.com/Nandeep2750/claude-profiles/actions/workflows/ci.yml/badge.svg)](https://github.com/Nandeep2750/claude-profiles/actions/workflows/ci.yml)
[![Docs](https://github.com/Nandeep2750/claude-profiles/actions/workflows/docs.yml/badge.svg)](https://github.com/Nandeep2750/claude-profiles/actions/workflows/docs.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platforms](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20WSL%20%7C%20Windows-blue)

### [📖 Read the documentation](https://nandeep2750.github.io/claude-profiles/)

</div>

---

## The problem

Claude Code stores one login. Signing into a second account logs the first one
out, and each account can only see its own conversation history.

| | Without profiles | With profiles |
|---|---|---|
| **Work + personal accounts** | re-authenticate every switch | both signed in, switch instantly |
| **Hit a usage limit** | stuck, even if another account has capacity | hand the conversation over and continue |
| **Client projects** | easy to use the wrong account | the right account is picked on `cd` |

## Quick start

**macOS, Linux, WSL or Git-Bash**

```sh
git clone https://github.com/Nandeep2750/claude-profiles.git ~/.claude-tools
sh ~/.claude-tools/install.sh
exec $SHELL -l
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/Nandeep2750/claude-profiles.git $HOME\.claude-tools
pwsh -File $HOME\.claude-tools\install.ps1
```

Then add an account:

```sh
claude-profile work      # creates the profile
claude                   # then /login
```

See what you have:

```console
$ claude-profiles
╭───────────┬─────────────────────┬──────┬────────┬───────────┬───────┬───────────┬────────────╮
│ PROFILE   │ ACCOUNT             │ AUTH │ 5-HOUR │ RESETS    │ 7-DAY │ RESETS    │      AS OF │
├───────────┼─────────────────────┼──────┼────────┼───────────┼───────┼───────────┼────────────┤
│ * default │ you@example.com     │ ok   │    59% │ in 53m    │   40% │ in 4d 23h │     1h ago │
│   work    │ you@company.com     │ ok   │     3% │ in 1h 13m │   87% │ in 2d 18h │     2h ago │
│   client  │ (not logged in)     │ none │      - │ -         │     - │ -         │ never used │
╰───────────┴─────────────────────┴──────┴────────┴───────────┴───────┴───────────┴────────────╯
```

Two accounts signed in at once is normal — that is the whole point. The usage
columns tell you which account has room **before** you start, rather than
finding out mid-conversation. Both limits are shown because they run on separate
clocks: `work` above is fine for the next five hours but 87% through its week.

Those figures are cached. For current ones:

```sh
claude-profiles --live
```

Fetches each signed-in account in parallel and costs **no model tokens** — it
reads a usage endpoint, it does not run a prompt. Failures fall back to the
cached value rather than breaking the table.

## Commands

| Command | Does |
|---|---|
| `claude-profiles` | List every profile and which account is signed into it |
| `claude-profile NAME` | Switch to `NAME`, creating it if needed |
| `claude-sessions` | List this directory's conversations, readably |
| `claude-handoff NAME` | Copy this directory's latest conversation to another account |
| `claude-profile-remove NAME` | Delete a profile, its conversations and its credentials |
| `claude-profile-exec NAME CMD` | Run one command under a profile without switching |
| `claude-profile-clone SRC DST` | Seed a profile's settings from another one |
| `claude-doctor` | Check the installation for problems |
| `claude-profiles --live` | Current usage instead of the cached snapshot |

Tab completion works on all of them.
[Full reference →](https://nandeep2750.github.io/claude-profiles/commands/)

## Per-project accounts

Drop a marker file anywhere in a project tree — the nearest one wins, walking
up from the current directory:

```sh
echo work > ~/Projects/Acme/.claude-profile     # covers every repo under Acme/
```

Now `cd` anywhere under `~/Projects/Acme` selects the `work` account
automatically. Everywhere else falls back to `default`.
[More →](https://nandeep2750.github.io/claude-profiles/guides/per-project/)

## Session handoff

You are 50 messages into a conversation. Claude knows your whole problem. Then
you hit your usage limit — but your other account has capacity.

```sh
claude-handoff work
```

That copies the conversation into the other account's history and prints the
command to continue it. Same conversation, same memory, different account
paying. Like forwarding an email thread to your other address.

It is a copy, so the original account keeps its version. Your code, folder and
git branch are untouched.
[More →](https://nandeep2750.github.io/claude-profiles/guides/handoff/)

## How it works

Claude Code reads `CLAUDE_CONFIG_DIR`, and derives its credential slot from that
path:

| Platform | Credentials stored in |
|---|---|
| macOS | Keychain, service `Claude Code-credentials-<sha256(dir)[:8]>` |
| Linux / WSL / Windows | `<profile dir>/.credentials.json` |

So each profile gets its own login, and signing into one cannot disturb another.
Nothing here patches Claude Code — it sets an environment variable Claude Code
already reads, and copies transcript files Claude Code already understands.
Remove it and `claude` keeps working unchanged.
[Details →](https://nandeep2750.github.io/claude-profiles/how-it-works/)

## Two directories, kept apart

| Path | Holds | Synced |
|---|---|---|
| `~/.claude-tools` | this repo — logic, shell layers, installers | yes |
| `~/.claude-profiles` | credentials, transcripts, per-account config | **never** |

Account data stays machine-local. Run `/login` once per profile on each machine.

Profiles also share nothing with **each other** — MCP servers, plugins, settings
and conversation history are all per-profile, and nothing is inherited from
`~/.claude`. The one exception is files inside a project folder (`.mcp.json`,
`CLAUDE.md`), which every profile reads.
[What's shared, what isn't →](https://nandeep2750.github.io/claude-profiles/isolation/)

> [!WARNING]
> On macOS a profile's Keychain entry is keyed to its **absolute path**. Moving
> or renaming a profile directory after logging in invalidates its credentials.

## Settings

Set these before the `source` line in your rc file:

| Variable | Effect |
|---|---|
| `CLAUDE_DEFAULT_PROFILE` | where unmarked directories fall back to (default: `default`) |
| `CLAUDE_PROFILE_PROMPT=1` | show the active profile in your prompt |
| `CLAUDE_PROFILE_HOME` | where account data lives (default: `~/.claude-profiles`) |

[All settings →](https://nandeep2750.github.io/claude-profiles/settings/)

## Requirements

`python3`, [Claude Code](https://claude.com/claude-code), and zsh, bash or
PowerShell.

## Documentation

- **[Getting started](https://nandeep2750.github.io/claude-profiles/getting-started/)** — install and first profile
- **[Commands](https://nandeep2750.github.io/claude-profiles/commands/)** — every command and flag
- **[What's shared, what isn't](https://nandeep2750.github.io/claude-profiles/isolation/)** — profile isolation, and the one exception
- **[How it works](https://nandeep2750.github.io/claude-profiles/how-it-works/)** — mechanism and storage layout
- **[Settings](https://nandeep2750.github.io/claude-profiles/settings/)** — environment variables
- **[Troubleshooting](https://nandeep2750.github.io/claude-profiles/troubleshooting/)** — common problems and fixes
- **[Changelog](CHANGELOG.md)** — what changed, and when

## Contributing

Issues and pull requests are welcome.

Run the tests:

```sh
python3 -m unittest discover -s tests -v   # core
bash tests/test_shell.sh                   # shell layer, bash
zsh  tests/test_shell.sh                   # shell layer, zsh
```

Everything runs against a throwaway `HOME`, so your real profiles and
credentials are never touched. CI runs the same suite on Ubuntu and macOS
against Python 3.9 and 3.13, plus a PowerShell check on Windows.

Preview the docs locally:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-docs.txt
.venv/bin/mkdocs serve
```

## License

[MIT](LICENSE)
