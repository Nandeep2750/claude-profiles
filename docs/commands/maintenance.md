# Health and updates

Checking the install, and moving to a newer version.

---

## `claude-profiles doctor`

Checks the installation and reports anything wrong. Also available as
`claude-doctor`.

```
environment
  ok   python3 found at /usr/bin/python3
  ok   claude found at /usr/local/bin/claude
  ok   CLAUDE_CONFIG_DIR unset (profile 'default')
  ok   account data at ~/.claude-profiles (not a git repo)

shell wiring
  ok   .zshrc -> claude-profiles.zsh

profiles
  ok   default: you@example.com
  warn work: not logged in - run 'claude-profile work' then /login

keychain
  ok   Claude Code-credentials
  FAIL Claude Code-credentials-1a2b3c4d is orphaned - no profile maps to it

project markers
  ok   ~/projects/<project-name>/.claude-profile -> work

1 problem(s), 1 warning(s)
```

What it checks:

| Area | Looks for |
|---|---|
| environment | `python3` and `claude` on `PATH`; `CLAUDE_CONFIG_DIR` pointing somewhere real; account data not accidentally turned into a git repo |
| shell wiring | exactly one `source` line per rc file, pointing at a file that exists |
| profiles | which are signed in; `.credentials.json` not readable by other users |
| keychain | macOS entries that no longer map to any profile - left behind by deleting a profile with `rm -rf` |
| project markers | `.claude-profile` files that are empty or name a profile that does not exist |

Exits non-zero if it finds problems, so it works in a script. Warnings alone
exit zero - "not logged in" is a normal state, not a fault.

---

---

## `claude-update`

Check for and pull a newer version. Covered in full on the
[Updating](../internals/updating.md) page.

```sh
claude-update --check    # what is installed, and what is available
claude-update            # pull it
```

| Flag | Effect |
|---|---|
| `-c`, `--check` | report only, change nothing |

It refuses to run over uncommitted local edits, and uses `git pull --ff-only`.

It also tells you whether the change needs a shell restart. Changes under `bin/`
take effect immediately; changes under `shell/` do not.

---
