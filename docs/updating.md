# Updating

## Check your version

```sh
claude-update --check
```

```
installed: 1.4.0 (v1.4.0)
available: 1.4.0  (you are up to date)
```

!!! note "Version numbers on this page are illustrative"
    The current release is the badge at the top of the
    [README](https://github.com/Nandeep2750/claude-profiles#readme), or the
    [releases page](https://github.com/Nandeep2750/claude-profiles/releases).
    `claude-update --check` always compares against the live latest.

`claude-doctor` prints the same version on its first line, and
`claude-profiles --version` prints just the number.

The version string carries the git description too, so `1.4.0 (v1.4.0-3-gabc1234)`
means three commits past the tag, and a `-dirty` suffix means you have
uncommitted local changes.

## Update

```sh
claude-update
```

It checks GitHub for a newer release, runs `git pull --ff-only` in your
`~/.claude-tools` checkout, and shows what changed:

```
installed: 1.4.0 (v1.4.0)
available: 1.5.0  https://github.com/Nandeep2750/claude-profiles/releases/tag/v1.5.0

git pull --ff-only

a1b2c3d -> e4f5g6h
  feat: claude-update
  docs: updating page

the shell layer changed - run 'exec $SHELL -l' or open a new terminal
```

That last line matters. Changes under `bin/` take effect immediately, because
the shell functions launch the Python core fresh on every call. Changes under
`shell/` - new commands, completions, the `cd` hook - need already-open shells
reloaded. `claude-update` tells you which kind you just got, so you only restart
when it is actually necessary.

## Safety

- **`--ff-only`** - the update refuses to merge or rebase. If your checkout has
  diverged it stops rather than creating a merge commit.
- **Local changes block it.** If you have edited anything, it lists what and
  stops. Commit or stash first.
- **Account data is never touched.** Updating only pulls `~/.claude-tools`.
  Your profiles, credentials and conversations live in `~/.claude-profiles` and
  are not part of the repo.

## If you did not install with git

```sh
cd ~/.claude-tools && git pull
```

only works on a git checkout. If you copied the folder across by hand,
`claude-update` will say so - re-copy it, or convert to a checkout:

```sh
rm -rf ~/.claude-tools
git clone https://github.com/Nandeep2750/claude-profiles.git ~/.claude-tools
sh ~/.claude-tools/install.sh
```

Reinstalling is safe and idempotent: it will not duplicate the `source` line in
your rc file, and it does not touch account data.

## Pinning a version

```sh
cd ~/.claude-tools
git checkout v1.4.0     # any tag from the releases page
```

`claude-update` will then report a newer release available but refuse to pull,
because a detached checkout is not fast-forwardable. Return with
`git checkout main`.

## Release history

Every release is listed on
[GitHub](https://github.com/Nandeep2750/claude-profiles/releases) and in the
[changelog](https://github.com/Nandeep2750/claude-profiles/blob/main/CHANGELOG.md).
