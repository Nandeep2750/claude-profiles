# What's shared, what isn't

**Short version:** profiles share nothing. Each one is a complete, separate copy
of Claude Code's configuration. The only things shared are files that live
inside your project folders.

## Nothing is inherited

Claude Code writes to whichever directory `CLAUDE_CONFIG_DIR` points at, and
never looks anywhere else. There is no fallback to `~/.claude`.

The clearest demonstration: create a new profile while your original account is
signed in, and it reports `Not logged in`. If profiles inherited anything, it
would have picked up those credentials.

```console
$ claude-profiles
   PROFILE  CONFIG DIR                        ACCOUNT                  AUTH
*  default  ~/.claude                         you@example.com          ok
   work     ~/.claude-profiles/work           (not logged in)          none
```

## What that means day to day

| You do this in one profile | In another profile you get |
|---|---|
| Add an MCP server | not there - add it again |
| Approve a project's trust prompt | asked again |
| Install a plugin | not there |
| Change a setting | not there |
| Add a skill or agent | not there |
| Have 50 conversations | sees none of them |

That last row is exactly why [session handoff](guides/handoff.md) exists. The
other account is not hiding your conversation - it genuinely cannot see the
file, so handoff physically copies it.

## The one exception: project files

Anything stored **inside a project folder** is shared, because it belongs to the
repo rather than to your account.

```
~/Projects/Acme/api/
  .mcp.json      <- every profile reads this
  CLAUDE.md      <- every profile reads this
  .claude/       <- every profile reads this
```

So a project that ships its own MCP servers gives them to whichever account you
use there.

!!! note "Approval is still per-profile"
    The `.mcp.json` file is shared, but *permission to use it* is stored in your
    config directory. The first time you open that project under a new profile,
    Claude Code asks again whether to trust the project's MCP servers.

## The rule

| Where it lives | Shared between profiles |
|---|---|
| `~/.claude` or `~/.claude-profiles/<name>/` | :material-close: no - per-profile |
| inside the project folder | :material-check: yes |

## Why this is usually what you want

**Real separation.** A client account cannot accidentally pick up your personal
MCP servers, credentials, plugins, or chat history. Nothing leaks between
contexts.

**The trade-off:** every new profile starts empty and needs setting up.

## Setting up a new profile faster

Copy the pieces you want from an existing profile:

```sh
cp    ~/.claude/settings.json ~/.claude-profiles/work/
cp -R ~/.claude/plugins       ~/.claude-profiles/work/
cp -R ~/.claude/skills        ~/.claude-profiles/work/   # if you have any
```

Global MCP servers are registered in `.claude.json`, so re-add them with the CLI
while that profile is active:

```sh
claude-profile work
claude mcp add <name> ...
```

!!! danger "Never copy `.credentials.json`"
    It belongs to one account. Copying it does not give you two logins - it
    gives you two profiles pointing at the same account, and signing out of one
    breaks both.

## Checking what a profile has

```sh
ls ~/.claude-profiles/work          # what this profile has accumulated
claude-profiles                     # which account is in each
```

A profile directory fills up on its own as you use it - `projects/`,
`sessions/`, `history.jsonl`, caches. Differences between profiles are normal
and mean nothing is wrong.
