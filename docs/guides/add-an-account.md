# Add an account

```sh
claude-profile work      # creates ~/.claude-profiles/work on first use
claude                   # then type /login
```

That is the whole process. Your existing account is untouched - it stays
available as `default`.

## Check it worked

```sh
claude-profiles
```

```
   PROFILE  CONFIG DIR                        ACCOUNT                  AUTH
*  work     ~/.claude-profiles/work           you@company.com          ok
   default  ~/.claude                         you@example.com          ok
```

`AUTH ok` on both rows means both accounts are signed in simultaneously.

## Naming

Profiles are created by being named - there is no registry file to edit. That
also means a typo silently creates a new empty profile rather than erroring:

```sh
claude-profile porofed        # creates "porofed", reports (not logged in)
```

!!! tip
    If a profile looks unexpectedly logged out, run `claude-profiles` and check
    the list for a near-miss name. Remove the accidental one with
    `rm -rf ~/.claude-profiles/porofed`.

`default` is reserved. It means "no `CLAUDE_CONFIG_DIR` set", i.e. the stock
`~/.claude`, and is not a directory under `~/.claude-profiles`.

## Profiles do not share settings

Setting `CLAUDE_CONFIG_DIR` relocates everything, not just the login: settings,
MCP servers, plugins, permissions and session history are all per-profile. That
is usually what you want for work/client separation, but it does mean a new
profile starts empty. Full detail:
[What's shared, what isn't](../isolation.md).

To copy settings across:

```sh
cp ~/.claude/settings.json ~/.claude-profiles/work/
```

!!! danger "Never copy `.credentials.json` between profiles"
    It belongs to one account. Copying it does not give you two logins - it
    gives you two profiles pointing at the same account.

## Run one command under a profile

Without switching your shell:

```sh
CLAUDE_CONFIG_DIR=$(claude-profiles.py path work) claude -p "summarise this repo"
```

## Remove an account

```sh
rm -rf ~/.claude-profiles/work
```

That logs out only that account and removes it from the listing.
