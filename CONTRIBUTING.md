# Contributing

Thanks for taking the time. Bug reports, questions and pull requests are all
welcome.

## Getting set up

```sh
git clone https://github.com/Nandeep2750/claude-profiles.git
cd claude-profiles
sh install.sh          # wires your shell to this checkout
```

## Running the tests

```sh
python3 -m unittest discover -s tests -v   # core logic
bash tests/test_shell.sh                   # shell wiring, bash
zsh  tests/test_shell.sh                   # shell wiring, zsh
bash tests/test_e2e.sh                     # every command, run for real
zsh  tests/test_e2e.sh
bash tests/test_docs_commands.sh           # every command the docs promise
zsh  tests/test_docs_commands.sh
```

Four layers, on purpose: the unit tests exercise the core directly, the
shell tests check the wiring, the end-to-end tests run every user-facing command
through the shell wrappers, and `test_docs_commands.sh` extracts every command
from the documentation and runs that. A command can pass the first three and
still be wrong in the docs, or work in a normal shell and break in one running
`set -u` - both have happened.

Every test runs against a throwaway `HOME`, so your real profiles, credentials
and conversations are never touched. If a test ever needs the real ones,
something is wrong with the test.

## Linting

```sh
pipx run ruff check .
shellcheck --severity=warning shell/claude-profiles.bash install.sh tests/test_shell.sh
```

CI runs both, plus the full suite on Ubuntu and macOS across Python 3.9 and
3.13, in bash and zsh, and a PowerShell check on Windows.

## How the pieces fit

```
bin/claude-profiles.py     all the logic, cross-platform
shell/claude-profiles.zsh  thin wrappers, cd hook, completion
shell/claude-profiles.bash the same for bash
shell/ClaudeProfiles.psm1  the same for PowerShell
```

Logic belongs in the Python core so all three shells get it at once. The shell
layers should only do things a subprocess cannot: exporting into the current
shell, hooking `cd`, and completion.

**Changes under `bin/` take effect immediately** - the wrappers launch the core
fresh each call. **Changes under `shell/` need a restarted shell.**

## Things to know before changing code

- **Profile names become directory paths.** Anything that accepts a name must go
  through `check_name()` (or `_claude_valid_name` in shell). `remove` deletes
  what a name resolves to, so a name like `../Documents` must never be accepted.
  There are regression tests for this - please keep them passing.
- **Never widen what `clone` copies** to include `.credentials.json`,
  `.claude.json`, or conversation history.
- **Two integrations are undocumented upstream**: the transcript format that
  `claude-sessions` parses, and the usage endpoint `--live` calls. Both must
  degrade gracefully rather than crash if Claude Code changes them.
- Keep output aligned by measuring with `vlen()`, never `len()` - colour codes
  are invisible but counted.

## Pull requests

- One change per PR, with a test covering it.
- Run the tests and both linters first.
- Update `docs/` if behaviour changed, and add a `CHANGELOG.md` entry under
  "Unreleased".

## Docs

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-docs.txt
.venv/bin/mkdocs serve
```
