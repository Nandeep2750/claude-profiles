# Per-project accounts

Put a `.claude-profile` file containing a profile name anywhere in a project
tree. The nearest one wins, walking up from the current directory.

```sh
echo work > ~/projects/<project-name>/.claude-profile
```

Now `cd` anywhere under `~/projects/<project-name>` selects the `work` profile
automatically:

```sh
cd ~/projects/<project-name>/api
claude-profile
```

```
claude profile: work
config dir    : ~/.claude-profiles/work
```

Directories with no marker fall back to `default`.

## One marker, many repos

Because the walk goes *upward*, a single marker above a group of repos covers
all of them:

```
~/projects/<project-name>/
  .claude-profile        <- contains "work"
  api/                   -> work
  web/                   -> work
  infra/                 -> work
```

Placing it above the repos also means it does not need to be committed or
gitignored.

## Overriding for one repo

A marker deeper in the tree wins over one higher up:

```
~/projects/<project-name>/
  .claude-profile        <- "work"
  api/
  experiment/
    .claude-profile      <- "personal", wins inside experiment/
```

## How it works

A shell hook (`chpwd` in zsh, `PROMPT_COMMAND` in bash) walks up from the
current directory looking for the file and switches to the name inside it.

It is plain shell with an early-exit guard when the directory has not changed,
so it costs nothing per prompt. It does not shell out to Python,
which would add noticeable latency to every `cd`.

!!! note "Already-running sessions are unaffected"
    `CLAUDE_CONFIG_DIR` is read when `claude` launches. Switching profiles does
    not change a session that is already open - restart it.

## Troubleshooting

```sh
cat ~/projects/<project-name>/.claude-profile   # should contain just the profile name
claude-profile                        # what is active right now?
```

Trailing whitespace is stripped, but the name must match a directory under
`~/.claude-profiles` exactly - it is case-sensitive.
