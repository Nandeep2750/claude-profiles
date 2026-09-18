# Troubleshooting

## `command not found: claude-profiles`

The shell was started before the tooling was installed, or the `source` line is
missing from your rc file.

```sh
exec $SHELL -l                       # reload this shell
grep claude-profiles ~/.zshrc        # or ~/.bashrc - is the source line there?
```

New terminals pick it up automatically; only already-open ones need reloading.
Re-run `sh ~/.claude-tools/install.sh` if the line is genuinely absent - it is
idempotent and will not duplicate anything.

## Tab completion does not work

Completion needs zsh's completion system initialised. The zsh layer does this
itself, but a later line in your `~/.zshrc` can override it. Check that the
`source` line is not being undone by a framework loaded afterwards
(oh-my-zsh, prezto, starship), and try moving it to the end of the file.

Press Tab twice - the first press may only insert a common prefix.

## A profile shows `(not logged in)` but I did log in

Most likely a typo created a second, empty profile. Profiles are created by
being named, so `claude-profile porofed` silently makes `porofed`.

```sh
claude-profiles                      # look for a near-miss name
rm -rf ~/.claude-profiles/porofed    # remove the accidental one
```

On macOS the other cause is a moved profile directory. The Keychain entry is
keyed to the absolute path, so relocating a profile orphans its credentials.
Move it back, or log in again at the new path.

## `claude --resume` cannot find the session I handed off

Three things to check, in order:

1. **Are you in the right directory?** Sessions are looked up by working
   directory. `cd` to the folder the conversation belongs to.
2. **Are you on the right profile?** `claude-profile` reports the active one.
3. **Did the copy land?** `claude-sessions -A -a` shows every session in every
   profile - find the id and confirm which profile now holds it.

## `no session found for <dir>`

`claude-handoff` and `claude-sessions` match on the working directory recorded
inside the transcript. You are probably in a different directory from the one
the conversation belongs to.

```sh
claude-sessions -a                   # every directory, to find where it lives
claude-handoff work -d ~/code/api    # or point at the directory explicitly
```

Note the profile matters too: if a directory has a `.claude-profile` marker,
`cd`ing there switches profiles, and the listing is profile-scoped. Use `-A` to
search across all of them.

## `ambiguous session prefix`

The prefix matched more than one session. The command lists the candidates -
pass more characters.

```sh
claude-handoff work 0a90            # instead of: claude-handoff work 0
```

## Summaries are blank or the listing looks wrong

`claude-sessions` parses Claude Code's transcript format, which is internal and
can change between releases. The other commands do not depend on it.

Check `scan()` in `bin/claude-profiles.py` against a recent transcript:

```sh
head -3 ~/.claude/projects/*/*.jsonl | python3 -m json.tool
```

## The `cd` auto-switch is not firing

```sh
cat ~/Projects/Acme/.claude-profile   # should contain just the profile name
claude-profile                        # what is active right now?
```

The nearest marker walking *up* from the current directory wins. A marker
inside a subdirectory overrides one at the top of the tree. Trailing whitespace
is stripped, but the name must match a directory under `~/.claude-profiles`
exactly - it is case-sensitive.

Changing an already-running `claude` is not possible; the profile is read at
launch. Restart it.

## Both accounts hit their limits

Handoff moves a conversation, not quota. Check what you actually have:

```sh
claude-profiles                       # which accounts exist and are signed in
```

Then run `/usage` inside a session to see that account's remaining limit.

## Clone or push fails: "Could not read from remote repository"

You have several GitHub accounts and plain `git@github.com:` resolved to the
wrong one. Use the host alias from your `~/.ssh/config`:

```sh
git remote set-url origin github-nandeep2750:Nandeep2750/claude-profiles.git
ssh -T github-nandeep2750                 # confirms which identity that alias uses
```

## Starting over

Removing a single profile logs out only that account:

```sh
rm -rf ~/.claude-profiles/work
```

Removing the tooling leaves every account intact:

```sh
rm -rf ~/.claude-tools
# then delete the source line from ~/.zshrc or ~/.bashrc
```

Your original account in `~/.claude` is never touched by any of this.
