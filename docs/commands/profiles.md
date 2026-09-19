# Switching profiles

Moving between accounts, and seeing which one is active.

---

## `claude-profile [NAME]`

Switch the current shell to a profile. With no argument, reports the active one.

```sh
claude-profile             # which profile am I on?
claude-profile work        # switch to "work" (created if it does not exist)
claude-profile default     # back to the original ~/.claude
```

Sets `CLAUDE_CONFIG_DIR` and `CLAUDE_PROFILE_NAME` in the current shell. It is a
shell function rather than a script because only a function can modify the
environment of the shell you are sitting in.

**Scope is per-shell.** Two terminal tabs can be on different accounts at the
same time. An already-running `claude` is unaffected - the variable is read at
launch, so restart it after switching.

`default` is a reserved name meaning "no `CLAUDE_CONFIG_DIR` set", i.e. the
stock `~/.claude`. It is not a directory under `~/.claude-profiles`.

---

---

## `claude-profiles`

List every profile, which account is signed into it, whether credentials are
present, and how much of each account's usage limit is consumed.

```
╭───────────┬─────────────────────┬──────┬────────┬───────────┬───────┬───────────┬────────────╮
│ PROFILE   │ ACCOUNT             │ AUTH │ 5-HOUR │ RESETS    │ 7-DAY │ RESETS    │      AS OF │
├───────────┼─────────────────────┼──────┼────────┼───────────┼───────┼───────────┼────────────┤
│ * default │ you@example.com     │ ok   │    59% │ in 53m    │   40% │ in 4d 23h │     1h ago │
│   work    │ you@company.com     │ ok   │     3% │ in 1h 13m │   87% │ in 2d 18h │     2h ago │
│   client  │ (not logged in)     │ none │      - │ -         │     - │ -         │ never used │
╰───────────┴─────────────────────┴──────┴────────┴───────────┴───────┴───────────┴────────────╯
```

| Column | Meaning |
|---|---|
| `*` | active in this shell |
| `ACCOUNT` | email read from that profile's `.claude.json` |
| `AUTH` | `ok` if credentials exist, `none` if `/login` is still needed |
| `5-HOUR` | percent of the rolling 5-hour limit used, and when it resets |
| `7-DAY` | percent of the weekly limit used, and when it resets |
| `AS OF` | how old the usage figures are |

Percentages are colour-coded: green below 75%, amber from 75%, red from 90%.
A `locked` cell means that limit is currently exhausted.

There are **two independent limits** with separate clocks, which is why both get
their own reset column. An account can be fine on one and nearly out on the
other - the example above shows `work` at 3% for the next five hours but 87%
through its week.

| Flag | Effect |
|---|---|
| `--dirs` | also show each profile's config directory |
| `--no-usage` | hide the usage columns |
| `--plain` | no borders - easier to pipe into `awk`, `grep` or a script |
| `--live` | fetch current figures from the API instead of using the cache |

!!! tip "Want current figures rather than a cached snapshot?"
    See [Usage and limits](usage.md).

---

## `claude-profiles path NAME`

Print a profile's config directory. Useful in scripts.

```sh
CLAUDE_CONFIG_DIR=$(claude-profiles path work) claude -p "summarise this repo"
```

That runs a single command under a profile without switching your shell. For an
easier way to do the same thing, see
[`claude-profile-exec`](manage.md#claude-profile-exec-profile-command-args).
