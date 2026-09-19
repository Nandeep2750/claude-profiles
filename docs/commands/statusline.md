# Status line

Inside a Claude Code session your shell prompt is hidden, which is exactly when
knowing the account matters most. The status line puts it back.

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
[Updating](../internals/updating.md) page.

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
