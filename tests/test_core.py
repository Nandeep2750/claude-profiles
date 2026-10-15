#!/usr/bin/env python3
"""Tests for the claude-profiles core.

Every test runs against a throwaway HOME built from fixtures, so nothing
touches the real profiles or Keychain.
"""
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout

CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "bin", "claude-profiles.py")


def _read_json(path):
    with open(path) as fh:
        return json.load(fh)


def load_core(home, profile_home=None, config_dir=None):
    """Import the core fresh with HOME pointed at a fixture."""
    # expanduser("~") reads HOME on POSIX but USERPROFILE on Windows - set both,
    # and clear HOMEDRIVE/HOMEPATH which Windows consults before HOME.
    os.environ["HOME"] = home
    os.environ["USERPROFILE"] = home
    os.environ.pop("HOMEDRIVE", None)
    os.environ.pop("HOMEPATH", None)
    os.environ["USER"] = os.environ.get("USER") or os.environ.get("USERNAME") or "tester"
    os.environ["CLAUDE_PROFILE_HOME"] = profile_home or os.path.join(home, ".claude-profiles")
    os.environ.pop("CLAUDE_CONFIG_DIR", None)
    if config_dir:
        os.environ["CLAUDE_CONFIG_DIR"] = config_dir
    os.environ["NO_COLOR"] = "1"
    spec = importlib.util.spec_from_file_location("cp_core", CORE)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def encode_dir(path):
    """A projects/ directory name for a working directory.

    Mirrors Claude Code's scheme (separators and dots become dashes). The colon
    in a Windows drive letter is also replaced, since ':' is illegal in a
    Windows filename. The core never constructs these names - it reuses whatever
    directory a transcript already lives in - so this only has to be legal and
    consistent within the tests.
    """
    return "-" + (path.replace(os.sep, "-").replace("/", "-")
                      .replace(":", "-").replace(".", "-").strip("-"))


def transcript(path, cwd, prompts, branch="main"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        for p in prompts:
            fh.write(json.dumps({"type": "user", "cwd": cwd, "gitBranch": branch,
                                 "message": {"content": p}}) + "\n")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="cp-test-")
        self.ph = os.path.join(self.home, ".claude-profiles")
        os.makedirs(os.path.join(self.home, ".claude"), exist_ok=True)
        os.makedirs(self.ph, exist_ok=True)
        # default profile: logged in, with usage
        with open(os.path.join(self.home, ".claude.json"), "w") as fh:
            json.dump({"oauthAccount": {"emailAddress": "me@example.com"},
                       "cachedUsageUtilization": {
                           "fetchedAtMs": int(time.time() * 1000) - 3600_000,
                           "utilization": {
                               "five_hour": {"utilization": 59, "resets_at": None},
                               "seven_day": {"utilization": 40, "resets_at": None}}}}, fh)
        with open(os.path.join(self.home, ".claude", ".credentials.json"), "w") as fh:
            json.dump({"claudeAiOauth": {"accessToken": "fake-default"}}, fh)
        # work profile: logged in via credentials file
        w = os.path.join(self.ph, "work")
        os.makedirs(w, exist_ok=True)
        with open(os.path.join(w, ".claude.json"), "w") as fh:
            json.dump({"oauthAccount": {"emailAddress": "me@work.com"}}, fh)
        with open(os.path.join(w, ".credentials.json"), "w") as fh:
            json.dump({"claudeAiOauth": {"accessToken": "fake"}}, fh)  # noqa
        os.chmod(os.path.join(w, ".credentials.json"), 0o600)
        # empty profile
        os.makedirs(os.path.join(self.ph, "empty"), exist_ok=True)
        self.core = load_core(self.home)

    def tearDown(self):
        shutil.rmtree(self.home, ignore_errors=True)

    def run_cmd(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        old = sys.argv
        sys.argv = ["claude-profiles", *argv]
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = self.core.main()
        except SystemExit as e:
            code = e.code
        finally:
            sys.argv = old
        return code, out.getvalue(), err.getvalue()


class TestDiscovery(Fixture):
    def test_lists_default_first_then_sorted(self):
        self.assertEqual(self.core.profile_names(), ["default", "empty", "work"])

    def test_profile_dir_resolution(self):
        self.assertEqual(self.core.profile_dir("default"),
                         os.path.join(self.home, ".claude"))
        self.assertEqual(self.core.profile_dir("work"), os.path.join(self.ph, "work"))

    def test_active_profile_follows_config_dir(self):
        self.assertEqual(self.core.active_profile(), "default")
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.ph, "work")
        self.assertEqual(self.core.active_profile(), "work")

    def test_hidden_dirs_are_not_profiles(self):
        os.makedirs(os.path.join(self.ph, ".hidden"), exist_ok=True)
        self.assertNotIn(".hidden", self.core.profile_names())


class TestNameValidation(Fixture):
    """A profile name becomes a directory that `remove` will delete."""

    BAD = ["../Documents", "..", "../../etc", "a/b", "/etc", "",
           ".hidden", "-leading", "a\\b", "with space", "..\\..\\x"]

    def test_traversal_names_are_rejected(self):
        for name in self.BAD:
            with self.assertRaises(self.core.BadProfileName, msg=f"accepted {name!r}"):
                self.core.check_name(name)

    def test_profile_dir_rejects_traversal(self):
        for name in ("../Documents", "..", "a/b"):
            with self.assertRaises(self.core.BadProfileName):
                self.core.profile_dir(name)

    def test_remove_cannot_escape_the_profile_home(self):
        outside = os.path.join(self.home, "Documents")
        os.makedirs(outside, exist_ok=True)
        with open(os.path.join(outside, "keepme.txt"), "w") as fh:
            fh.write("important")
        code, _, err = self.run_cmd("remove", "../Documents", "--yes")
        self.assertEqual(code, 2)
        self.assertIn("invalid profile name", err)
        self.assertTrue(os.path.isfile(os.path.join(outside, "keepme.txt")),
                        "remove escaped CLAUDE_PROFILE_HOME")

    def test_clone_cannot_escape_the_profile_home(self):
        code, _, err = self.run_cmd("clone", "work", "../Documents")
        self.assertEqual(code, 2)
        self.assertIn("invalid profile name", err)

    def test_ordinary_names_are_accepted(self):
        for name in ("work", "client-a", "team_2", "v1.2", "default", "a"):
            self.assertEqual(self.core.check_name(name) if name != "default" else "default",
                             name)


class TestCredentials(Fixture):
    def test_credentials_file_counts_as_logged_in(self):
        self.assertTrue(self.core.has_credentials(os.path.join(self.ph, "work")))

    def test_empty_profile_is_not_logged_in(self):
        self.assertFalse(self.core.has_credentials(os.path.join(self.ph, "empty")))

    def test_keychain_service_is_path_derived_and_stable(self):
        a = self.core.keychain_service(os.path.join(self.ph, "work"))
        b = self.core.keychain_service(os.path.join(self.ph, "work"))
        c = self.core.keychain_service(os.path.join(self.ph, "other"))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("Claude Code-credentials-"))

    def test_default_uses_the_unhashed_service(self):
        self.assertEqual(self.core.keychain_service(os.path.join(self.home, ".claude")),
                         "Claude Code-credentials")

    def test_access_token_read_from_file(self):
        self.assertEqual(self.core.access_token(os.path.join(self.ph, "work")), "fake")

    def test_access_token_missing_is_none(self):
        self.assertIsNone(self.core.access_token(os.path.join(self.ph, "empty")))


class TestUsage(Fixture):
    def test_reads_cached_usage(self):
        u = self.core.usage_of(os.path.join(self.home, ".claude"))
        self.assertEqual(u["5h"]["pct"], 59)
        self.assertEqual(u["7d"]["pct"], 40)
        self.assertGreater(u["age"], 0)

    def test_live_results_are_persisted_and_win_over_a_stale_cache(self):
        d = os.path.join(self.home, ".claude")          # has a 1h-old CC cache
        stale = self.core.usage_of(d)
        self.assertGreater(stale["age"], 1800)
        self.core.save_usage(d, {"5h": {"pct": 7, "resets": None, "locked": None},
                                 "7d": {"pct": 8, "resets": None, "locked": None}})
        fresh = self.core.usage_of(d)
        self.assertEqual(fresh["5h"]["pct"], 7)
        self.assertLess(fresh["age"], 5, "the newer cache should win")

    def test_a_stale_own_cache_loses_to_a_fresh_claude_code_one(self):
        d = os.path.join(self.home, ".claude")
        import json as _json
        with open(os.path.join(d, ".usage-cache.json"), "w") as fh:
            _json.dump({"fetchedAtMs": int((time.time() - 86400) * 1000),
                        "utilization": {"5h": {"pct": 99}, "7d": {"pct": 99}}}, fh)
        # Claude Code's cache in the fixture is 1h old, so it should win
        self.assertEqual(self.core.usage_of(d)["5h"]["pct"], 59)

    def test_save_usage_is_atomic_and_leaves_no_temp_file(self):
        d = os.path.join(self.ph, "work")
        self.core.save_usage(d, {"5h": {"pct": 1}, "7d": {"pct": 2}})
        self.assertTrue(os.path.isfile(os.path.join(d, ".usage-cache.json")))
        self.assertFalse(os.path.exists(os.path.join(d, ".usage-cache.json.tmp")))

    def test_corrupt_own_cache_is_ignored(self):
        d = os.path.join(self.home, ".claude")
        with open(os.path.join(d, ".usage-cache.json"), "w") as fh:
            fh.write("{not json")
        self.assertEqual(self.core.usage_of(d)["5h"]["pct"], 59)   # falls back

    def test_absent_usage_is_none(self):
        self.assertIsNone(self.core.usage_of(os.path.join(self.ph, "empty")))

    def test_buckets_accepts_nested_flat_and_limits(self):
        b = self.core._buckets
        self.assertEqual(b({"utilization": {"five_hour": {"utilization": 42}}})["5h"]["pct"], 42)
        self.assertEqual(b({"five_hour": {"utilization": 7}})["5h"]["pct"], 7)
        got = b({"limits": [{"group": "session", "percent": 13},
                            {"group": "seven_day", "percent": 88}]})
        self.assertEqual((got["5h"]["pct"], got["7d"]["pct"]), (13, 88))

    def test_buckets_on_junk_is_empty_not_an_error(self):
        self.assertEqual(self.core._buckets({}), {"5h": None, "7d": None})

    def test_live_fetch_without_token_says_so(self):
        usage, why = self.core.fetch_live(os.path.join(self.ph, "empty"))
        self.assertIsNone(usage)
        self.assertEqual(why, "not logged in")

    def test_live_fetch_reports_unreachable(self):
        old = self.core.USAGE_URL
        self.core.USAGE_URL = "https://127.0.0.1:9/nope"
        try:
            usage, why = self.core.fetch_live(os.path.join(self.ph, "work"), timeout=2)
        finally:
            self.core.USAGE_URL = old
        self.assertIsNone(usage)
        self.assertEqual(why, "unreachable")

    def test_token_expiry_is_read(self):
        w = os.path.join(self.ph, "work")
        with open(os.path.join(w, ".credentials.json"), "w") as fh:
            json.dump({"claudeAiOauth": {"accessToken": "fake",
                                         "expiresAt": 1700000000000}}, fh)
        self.assertEqual(self.core.token_expiry(w), 1700000000.0)

    def test_token_expiry_absent_is_none(self):
        self.assertIsNone(self.core.token_expiry(os.path.join(self.ph, "empty")))

    def test_until_and_ago_formatting(self):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        soon = (now + datetime.timedelta(minutes=30)).isoformat()
        far = (now + datetime.timedelta(days=4, hours=23)).isoformat()
        self.assertTrue(self.core.until(soon).startswith("in "))
        self.assertIn("d ", self.core.until(far))          # "in 4d 23h"
        self.assertEqual(self.core.until(None), "-")
        self.assertEqual(self.core.ago(120), "2m ago")


class TestTable(Fixture):
    def test_ansi_codes_do_not_affect_width(self):
        self.assertEqual(self.core.vlen("\x1b[32mok\x1b[0m"), 2)
        self.assertEqual(self.core.vlen("ok"), 2)

    def test_every_rendered_row_is_the_same_width(self):
        t = self.core.render_table(["A", "B"], [["\x1b[32mgreen\x1b[0m", "x"], ["y", "zz"]])
        widths = {self.core.vlen(line) for line in t.splitlines()}
        self.assertEqual(len(widths), 1, f"rows differ in width: {widths}")

    def test_plain_mode_has_no_borders(self):
        t = self.core.render_table(["A"], [["x"]], plain=True)
        self.assertNotIn("│", t)


class TestSessions(Fixture):
    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        enc = encode_dir(self.proj)
        transcript(os.path.join(self.home, ".claude", "projects", enc, "aaa11111-0000-0000-0000-000000000000.jsonl"),
                   self.proj, ["fix the auth bug", "and the tests"])
        transcript(os.path.join(self.home, ".claude", "projects", enc, "bbb22222-0000-0000-0000-000000000000.jsonl"),
                   self.proj, ["unrelated question"])

    def test_scan_extracts_cwd_turns_and_summary(self):
        f = [t for t in self.core.transcripts("default") if "aaa11111" in t][0]
        cwd, branch, turns, mtime, summary = self.core.scan(f)
        self.assertEqual(cwd, self.proj)
        self.assertEqual(turns, 2)
        self.assertEqual(summary, "fix the auth bug")
        self.assertEqual(branch, "main")

    def test_listing_finds_sessions_for_that_directory(self):
        code, out, _ = self.run_cmd("sessions", "-d", self.proj, "--plain")
        self.assertEqual(code, 0)
        self.assertIn("fix the auth bug", out)
        self.assertIn("aaa11111", out)

    def test_listing_elsewhere_finds_nothing(self):
        code, _, err = self.run_cmd("sessions", "-d", self.home, "--plain")
        self.assertEqual(code, 1)
        self.assertIn("no sessions", err)

    def test_tool_results_are_not_counted_as_turns(self):
        p = os.path.join(self.home, "t.jsonl")
        with open(p, "w") as fh:
            fh.write(json.dumps({"type": "user", "cwd": "/x",
                                 "message": {"content": [{"type": "tool_result"}]}}) + "\n")
            fh.write(json.dumps({"type": "user", "cwd": "/x",
                                 "message": {"content": "real question"}}) + "\n")
        _, _, turns, _, summary = self.core.scan(p)
        self.assertEqual(turns, 1)
        self.assertEqual(summary, "real question")

    def test_sidechains_are_ignored(self):
        p = os.path.join(self.home, "s.jsonl")
        with open(p, "w") as fh:
            fh.write(json.dumps({"type": "user", "cwd": "/x", "isSidechain": True,
                                 "message": {"content": "subagent chatter"}}) + "\n")
            fh.write(json.dumps({"type": "user", "cwd": "/x",
                                 "message": {"content": "the real one"}}) + "\n")
        self.assertEqual(self.core.scan(p)[4], "the real one")


class TestSearch(Fixture):
    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        enc = encode_dir(self.proj)
        transcript(os.path.join(self.home, ".claude", "projects", enc,
                                "ccc11111-0000-0000-0000-000000000000.jsonl"),
                   self.proj, ["fix the login redirect"])
        # a session whose only match is in an assistant reply
        p = os.path.join(self.home, ".claude", "projects", enc,
                         "ddd22222-0000-0000-0000-000000000000.jsonl")
        with open(p, "w") as fh:
            fh.write(json.dumps({"type": "user", "cwd": self.proj,
                                 "message": {"content": "what about storage?"}}) + "\n")
            fh.write(json.dumps({"type": "assistant", "cwd": self.proj,
                                 "message": {"content": "Use the macOS Keychain for that."}}) + "\n")

    def test_matches_a_user_message(self):
        code, out, _ = self.run_cmd("sessions", "-d", self.proj, "--plain", "-g", "redirect")
        self.assertEqual(code, 0)
        self.assertIn("ccc11111", out)
        self.assertNotIn("ddd22222", out)

    def test_matches_an_assistant_message(self):
        code, out, _ = self.run_cmd("sessions", "-d", self.proj, "--plain", "-g", "keychain")
        self.assertEqual(code, 0)
        self.assertIn("ddd22222", out)

    def test_search_is_case_insensitive(self):
        code, out, _ = self.run_cmd("sessions", "-d", self.proj, "--plain", "-g", "REDIRECT")
        self.assertEqual(code, 0)
        self.assertIn("ccc11111", out)

    def test_no_match_exits_one(self):
        code, _, err = self.run_cmd("sessions", "-d", self.proj, "--plain", "-g", "zzzznope")
        self.assertEqual(code, 1)
        self.assertIn("matching", err)

    def test_bad_regex_is_reported(self):
        code, _, err = self.run_cmd("sessions", "-d", self.proj, "-g", "[unclosed")
        self.assertEqual(code, 2)
        self.assertIn("bad --grep", err)

    def test_summary_shows_the_match_not_the_opening_prompt(self):
        code, out, _ = self.run_cmd("sessions", "-d", self.proj, "--plain", "-g", "keychain", "-f")
        self.assertIn("Keychain", out)
        self.assertNotIn("what about storage", out)


class TestShellParity(unittest.TestCase):
    """Every subcommand the core offers must be reachable from all three shell
    layers. The zsh and bash dispatch lists are checked by tests/test_shell.sh;
    PowerShell has no such harness, so it is checked here - this runs on
    Windows CI too."""

    def setUp(self):
        self.repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def core_subcommands(self):
        with open(os.path.join(self.repo, "bin", "claude-profiles.py")) as fh:
            src = fh.read()
        return sorted(set(re.findall(r'sub\.add_parser\("([a-z]+)"', src)))

    def test_the_core_offers_subcommands(self):
        self.assertGreater(len(self.core_subcommands()), 5)

    def test_powershell_dispatches_every_subcommand(self):
        with open(os.path.join(self.repo, "shell", "ClaudeProfiles.psm1")) as fh:
            psm1 = fh.read()
        block = re.search(r"\$script:Subcommands\s*=\s*@\((.*?)\)", psm1, re.S)
        self.assertIsNotNone(block, "ClaudeProfiles.psm1 has no $script:Subcommands list")
        listed = set(re.findall(r"'([a-z]+)'", block.group(1)))
        missing = sorted(set(self.core_subcommands()) - listed)
        self.assertEqual(missing, [],
                         f"claude-profiles on Windows would send these to status: {missing}")

    def test_the_shell_layers_dispatch_every_subcommand(self):
        for name in ("claude-profiles.zsh", "claude-profiles.bash"):
            with open(os.path.join(self.repo, "shell", name)) as fh:
                text = fh.read()
            line = re.search(r"^\s*([a-z|]+)\)\s*\"\$CLAUDE_PY\"", text, re.M)
            self.assertIsNotNone(line, f"{name} has no dispatch case")
            listed = set(line.group(1).split("|"))
            missing = sorted(set(self.core_subcommands()) - listed)
            self.assertEqual(missing, [], f"{name} would send these to status: {missing}")

    def test_each_shell_layer_has_a_wrapper_for_clear(self):
        for name, needle in (("claude-profiles.zsh", "claude-clear()"),
                             ("claude-profiles.bash", "claude-clear()"),
                             ("ClaudeProfiles.psm1", "claude-clear")):
            with open(os.path.join(self.repo, "shell", name)) as fh:
                self.assertIn(needle, fh.read(), name)

    def docs_text(self):
        import glob
        return "\n".join(open(f).read() for f in
                         sorted(glob.glob(os.path.join(self.repo, "docs", "**", "*.md"),
                                          recursive=True)))

    def test_every_subcommand_is_documented(self):
        missing = [s for s in self.core_subcommands() if s not in self.docs_text()]
        self.assertEqual(missing, [], f"undocumented subcommands: {missing}")

    def test_every_shell_command_is_documented(self):
        with open(os.path.join(self.repo, "shell", "claude-profiles.zsh")) as fh:
            names = sorted(set(re.findall(r"^(claude[-_][a-z-]+)\(\)", fh.read(), re.M)))
        self.assertGreater(len(names), 10)
        docs = self.docs_text()
        missing = [n for n in names if n not in docs]
        self.assertEqual(missing, [], f"undocumented commands: {missing}")

    def test_every_environment_variable_is_documented(self):
        texts = []
        for name in ("bin/claude-profiles.py", "shell/claude-profiles.zsh"):
            with open(os.path.join(self.repo, name)) as fh:
                texts.append(fh.read())
        names = set(re.findall(r'environ\.get\("(CLAUDE_[A-Z_]+)"', texts[0]))
        names |= set(re.findall(r"\$\{?(CLAUDE_[A-Z_]+)", texts[1]))
        docs = self.docs_text()
        missing = sorted(n for n in names if n not in docs)
        self.assertEqual(missing, [], f"undocumented settings: {missing}")

    def test_every_documented_command_exists_in_all_three_layers(self):
        """The docs promise the same claude-* names everywhere."""
        layers = {}
        for name in ("claude-profiles.zsh", "claude-profiles.bash",
                     "ClaudeProfiles.psm1"):
            with open(os.path.join(self.repo, "shell", name)) as fh:
                layers[name] = fh.read()
        with open(os.path.join(self.repo, "docs", "commands", "index.md")) as fh:
            documented = set(re.findall(r"`(claude-[a-z-]+)`", fh.read()))
        documented.discard("claude-profiles.py")
        for cmd in sorted(documented):
            for name, text in layers.items():
                self.assertIn(cmd, text, f"{name} has no {cmd}")


class TestPartialDelete(Fixture):
    """Delete some of a project's sessions and the rest must be untouched -
    transcript, side files, and every profile-level folder named after them."""

    IDS = [f"{n}{'a' * 7}-0000-0000-0000-000000000000" for n in range(1, 9)]

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        self.enc = encode_dir(self.proj)
        self.wdir = os.path.join(self.ph, "work")
        self.pdir = os.path.join(self.wdir, "projects", self.enc)
        for i, sid in enumerate(self.IDS, 1):
            transcript(os.path.join(self.pdir, sid + ".jsonl"), self.proj,
                       [f"session {i}"])
            self.belongings(sid, f"body of {sid}")

    def belongings(self, sid, body):
        """Everything on disk that one session owns."""
        made = []
        side = os.path.join(self.pdir, sid, "tool-results")
        os.makedirs(side, exist_ok=True)
        with open(os.path.join(side, "r1.txt"), "w") as fh:
            fh.write(body)
        made.append(os.path.join(side, "r1.txt"))
        for top, name in (("file-history", sid), ("session-env", sid),
                          ("tasks", sid), ("jobs", sid[:8])):
            d = os.path.join(self.wdir, top, name)
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "v1"), "w") as fh:
                fh.write(body)
            made.append(os.path.join(d, "v1"))
        mode = os.path.join(self.wdir, ".caveman-sessions", sid + ".mode")
        os.makedirs(os.path.dirname(mode), exist_ok=True)
        with open(mode, "w") as fh:
            fh.write(body)
        made.append(mode)
        return made

    def owns(self, sid):
        return ([os.path.join(self.pdir, sid + ".jsonl"),
                 os.path.join(self.pdir, sid, "tool-results", "r1.txt")]
                + [os.path.join(self.wdir, t, n, "v1")
                   for t, n in (("file-history", sid), ("session-env", sid),
                                ("tasks", sid), ("jobs", sid[:8]))]
                + [os.path.join(self.wdir, ".caveman-sessions", sid + ".mode")])

    def delete(self, *sids):
        args = ["clear", self.proj, "-p", "work", "--yes", "--plain"]
        for sid in sids:
            args += ["-s", sid]
        code, out, err = self.run_cmd(*args)
        self.assertEqual(code, 0, err)
        return out

    def assert_gone(self, sid):
        for path in self.owns(sid):
            self.assertFalse(os.path.exists(path), f"{sid} left behind {path}")

    def assert_intact(self, sid):
        for path in self.owns(sid):
            self.assertTrue(os.path.exists(path), f"{sid} lost {path}")
        with open(os.path.join(self.pdir, sid, "tool-results", "r1.txt")) as fh:
            self.assertEqual(fh.read(), f"body of {sid}")

    def test_all_eight_start_complete(self):
        for sid in self.IDS:
            self.assert_intact(sid)

    def test_deleting_four_leaves_the_other_four(self):
        doomed, kept = self.IDS[:4], self.IDS[4:]
        self.delete(*doomed)
        for sid in doomed:
            self.assert_gone(sid)
        for sid in kept:
            self.assert_intact(sid)

    def test_deleting_one_leaves_seven(self):
        self.delete(self.IDS[3])
        self.assert_gone(self.IDS[3])
        for sid in self.IDS[:3] + self.IDS[4:]:
            self.assert_intact(sid)

    def test_the_project_directory_survives_a_partial_delete(self):
        self.delete(*self.IDS[:4])
        self.assertTrue(os.path.isdir(self.pdir),
                        "the remaining sessions still live here")

    def test_the_shared_folders_survive_a_partial_delete(self):
        self.delete(*self.IDS[:4])
        for top in ("file-history", "session-env", "tasks", "jobs",
                    ".caveman-sessions"):
            self.assertTrue(os.path.isdir(os.path.join(self.wdir, top)),
                            f"{top} itself was removed")

    def test_the_projects_memory_survives_a_partial_delete(self):
        mem = os.path.join(self.pdir, "memory")
        os.makedirs(mem, exist_ok=True)
        with open(os.path.join(mem, "MEMORY.md"), "w") as fh:
            fh.write("- [a](a.md)\n")
        self.delete(*self.IDS[:4])
        self.assertTrue(os.path.isfile(os.path.join(mem, "MEMORY.md")))

    def test_sessions_listing_shows_exactly_the_four_that_are_left(self):
        self.delete(*self.IDS[:4])
        _, out, _ = self.run_cmd("sessions", "-p", "work", "-d", self.proj,
                                 "--plain")
        for sid in self.IDS[:4]:
            self.assertNotIn(sid[:8], out)
        for sid in self.IDS[4:]:
            self.assertIn(sid[:8], out)

    def test_doctor_reports_nothing_stranded_afterwards(self):
        self.delete(*self.IDS[:4])
        _, out, _ = self.run_cmd("doctor")
        self.assertIn("nothing is left over", out)

    def test_a_traces_sweep_afterwards_removes_nothing_more(self):
        self.delete(*self.IDS[:4])
        code, out, _ = self.run_cmd("prune", "--traces", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("nothing left over", out)
        for sid in self.IDS[4:]:
            self.assert_intact(sid)

    def test_a_shared_short_prefix_never_takes_the_other_sessions_job(self):
        # two sessions whose ids begin with the same eight characters
        twin_a = "cccccccc-0000-0000-0000-00000000000a"
        twin_b = "cccccccc-0000-0000-0000-00000000000b"
        for sid in (twin_a, twin_b):
            transcript(os.path.join(self.pdir, sid + ".jsonl"), self.proj, ["x"])
        job = os.path.join(self.wdir, "jobs", "cccccccc")
        os.makedirs(job, exist_ok=True)
        with open(os.path.join(job, "state.json"), "w") as fh:
            fh.write("{}")
        self.delete(twin_a)
        self.assertFalse(os.path.exists(os.path.join(self.pdir, twin_a + ".jsonl")))
        self.assertTrue(os.path.isfile(os.path.join(job, "state.json")),
                        "the surviving twin still needs that job")
        self.assertTrue(os.path.isfile(os.path.join(self.pdir, twin_b + ".jsonl")))

    def test_an_eight_hex_name_outside_jobs_is_not_a_session(self):
        cache = os.path.join(self.wdir, "cache", self.IDS[0][:8])
        os.makedirs(cache, exist_ok=True)
        with open(os.path.join(cache, "blob"), "w") as fh:
            fh.write("unrelated")
        self.delete(self.IDS[0])
        self.assertTrue(os.path.isfile(os.path.join(cache, "blob")),
                        "only jobs/ keys by a short id")


class TestPickParsing(Fixture):
    """The number picker. Anything it misreads deletes the wrong session."""

    def picks(self, text, n=5):
        return self.core.parse_picks(text, n)

    def test_single_number(self):
        self.assertEqual(self.picks("3"), [3])

    def test_a_list(self):
        self.assertEqual(self.picks("1,3,5"), [1, 3, 5])

    def test_a_range(self):
        self.assertEqual(self.picks("2-4"), [2, 3, 4])

    def test_mixed_and_deduplicated(self):
        self.assertEqual(self.picks("1, 2-4 3"), [1, 2, 3, 4])

    def test_spaces_instead_of_commas(self):
        self.assertEqual(self.picks("1 5"), [1, 5])

    def test_all(self):
        self.assertEqual(self.picks("all", 3), [1, 2, 3])
        self.assertEqual(self.picks("ALL", 3), [1, 2, 3])

    def test_empty_cancels(self):
        for text in ("", "  ", "q", "no", "none"):
            self.assertEqual(self.picks(text), [], text)

    def test_out_of_range_is_rejected(self):
        for text in ("0", "6", "1-6", "-1"):
            self.assertIsNone(self.picks(text), text)

    def test_a_backwards_range_is_rejected(self):
        self.assertIsNone(self.picks("4-2"))

    def test_junk_is_rejected(self):
        for text in ("x", "1;rm", "1.5", "2/3", "all the things"):
            self.assertIsNone(self.picks(text), text)


class TestTranscriptListing(Fixture):
    """transcripts() must yield sessions only. A subagent log inside
    <session-id>/ is part of a session, and prune once offered to delete it."""

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        self.enc = encode_dir(self.proj)
        self.pdir = os.path.join(self.home, ".claude", "projects", self.enc)
        self.sid = "aaa11111-0000-0000-0000-000000000000"
        transcript(os.path.join(self.pdir, self.sid + ".jsonl"), self.proj, ["hi"])

    def nested(self, *parts):
        path = os.path.join(self.pdir, self.sid, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("{}\n")
        return path

    def test_a_subagent_log_is_not_a_session(self):
        self.nested("subagents", "agent-abc123.jsonl")
        self.assertEqual([os.path.basename(f) for f in self.core.transcripts("default")],
                         [self.sid + ".jsonl"])

    def test_a_workflow_journal_is_not_a_session(self):
        self.nested("subagents", "workflows", "wf_1", "journal.jsonl")
        self.assertEqual(len(list(self.core.transcripts("default"))), 1)

    def test_prune_leaves_side_files_alone(self):
        log = self.nested("subagents", "agent-abc123.jsonl")
        long_ago = time.time() - 300 * 86400
        os.utime(log, (long_ago, long_ago))
        code, out, _ = self.run_cmd("prune", "-o", "90", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(log), "a session's side files are not sessions")

    def test_a_bak_is_not_listed_as_a_session(self):
        with open(os.path.join(self.pdir, "bbb22222-0000-0000-0000-000000000000.jsonl.bak"),
                  "w") as fh:
            fh.write("{}\n")
        self.assertEqual(len(list(self.core.transcripts("default"))), 1)

    def test_a_missing_projects_directory_is_not_an_error(self):
        self.assertEqual(list(self.core.transcripts("empty")), [])


class TestClear(Fixture):
    """clear takes a project path, lists that directory's sessions across every
    profile, and deletes the chosen ones with everything that belongs to them."""

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        self.sub = os.path.join(self.proj, "web")
        os.makedirs(self.sub, exist_ok=True)
        self.enc = encode_dir(self.proj)
        self.senc = encode_dir(self.sub)
        # one in the default profile, one in work, one in a subdirectory
        self.d_file = os.path.join(self.home, ".claude", "projects", self.enc,
                                   "aaa11111-0000-0000-0000-000000000000.jsonl")
        self.w_file = os.path.join(self.ph, "work", "projects", self.enc,
                                   "bbb22222-0000-0000-0000-000000000000.jsonl")
        self.s_file = os.path.join(self.ph, "work", "projects", self.senc,
                                   "ccc33333-0000-0000-0000-000000000000.jsonl")
        transcript(self.d_file, self.proj, ["one"])
        transcript(self.w_file, self.proj, ["two", "three"])
        transcript(self.s_file, self.sub, ["in a subdirectory"])

    def side_of(self, f):
        d = f[:-6]
        os.makedirs(os.path.join(d, "tool-results"), exist_ok=True)
        with open(os.path.join(d, "tool-results", "r1.txt"), "w") as fh:
            fh.write("payload")
        return d

    # ---- the path argument -------------------------------------------------
    def test_a_missing_path_is_refused(self):
        code, _, err = self.run_cmd("clear", os.path.join(self.home, "nope"))
        self.assertEqual(code, 1)
        self.assertIn("no such path", err)

    def test_a_missing_relative_path_says_where_it_was_read_from(self):
        here = os.getcwd()
        try:
            os.chdir(self.home)
            code, _, err = self.run_cmd("clear", "code/nope")
        finally:
            os.chdir(here)
        self.assertEqual(code, 1)
        self.assertIn("relative path", err)
        self.assertIn(self.home, err)

    def test_a_tilde_the_shell_left_alone_is_expanded(self):
        code, _, err = self.run_cmd("clear", "~/code/nope")
        self.assertEqual(code, 1)
        self.assertNotIn("relative path", err, "~ is not a relative path")

    def test_a_file_is_refused(self):
        code, _, err = self.run_cmd("clear", self.d_file)
        self.assertEqual(code, 1)
        self.assertIn("not a directory", err)

    def test_a_directory_with_no_sessions_says_so(self):
        code, out, _ = self.run_cmd("clear", self.home, "--plain")
        self.assertEqual(code, 0)
        self.assertIn("no sessions recorded", out)

    def test_an_unknown_profile_is_refused(self):
        code, _, err = self.run_cmd("clear", self.proj, "-p", "nosuch")
        self.assertEqual(code, 1)
        self.assertIn("no such profile", err)

    def test_a_traversal_profile_name_is_refused(self):
        code, _, err = self.run_cmd("clear", self.proj, "-p", "../escape")
        self.assertEqual(code, 1)
        self.assertIn("invalid profile name", err)

    # ---- listing -----------------------------------------------------------
    def test_lists_every_profile_for_that_path(self):
        code, out, _ = self.run_cmd("clear", self.proj, "--dry-run", "--all", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("aaa11111", out)
        self.assertIn("bbb22222", out)

    def test_a_subdirectory_session_is_left_out_by_default(self):
        _, out, _ = self.run_cmd("clear", self.proj, "--dry-run", "--all", "--plain")
        self.assertNotIn("ccc33333", out)

    def test_under_includes_subdirectories(self):
        _, out, _ = self.run_cmd("clear", self.proj, "-r", "--dry-run", "--all", "--plain")
        self.assertIn("ccc33333", out)

    def test_profile_narrows_the_list(self):
        _, out, _ = self.run_cmd("clear", self.proj, "-p", "work",
                                 "--dry-run", "--all", "--plain")
        self.assertIn("bbb22222", out)
        self.assertNotIn("aaa11111", out)

    # ---- choosing without a prompt -----------------------------------------
    def test_dry_run_deletes_nothing(self):
        code, out, _ = self.run_cmd("clear", self.proj, "--all", "--dry-run", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertTrue(os.path.isfile(self.d_file))
        self.assertTrue(os.path.isfile(self.w_file))

    def test_all_with_yes_deletes_both_copies(self):
        code, out, _ = self.run_cmd("clear", self.proj, "--all", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.d_file))
        self.assertFalse(os.path.exists(self.w_file))
        self.assertTrue(os.path.isfile(self.s_file), "a subdirectory session is not touched")

    def test_session_prefix_deletes_just_that_one(self):
        code, _, _ = self.run_cmd("clear", self.proj, "-s", "bbb22222", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.w_file))
        self.assertTrue(os.path.isfile(self.d_file))

    def test_a_session_not_in_the_list_is_refused(self):
        code, _, err = self.run_cmd("clear", self.proj, "-s", "zzz99999", "--yes")
        self.assertEqual(code, 1)
        self.assertIn("not in this list", err)
        self.assertTrue(os.path.isfile(self.d_file))

    def test_no_selection_without_a_terminal_is_refused(self):
        code, _, err = self.run_cmd("clear", self.proj, "--plain")
        self.assertEqual(code, 1)
        self.assertIn("nothing selected", err)
        self.assertTrue(os.path.isfile(self.d_file))

    # ---- what gets deleted -------------------------------------------------
    def test_the_side_files_go_with_the_session(self):
        side = self.side_of(self.w_file)
        code, _, _ = self.run_cmd("clear", self.proj, "-s", "bbb22222", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(side))

    def test_a_bak_goes_with_the_session(self):
        bak = self.w_file + ".bak"
        with open(bak, "w") as fh:
            fh.write("{}\n")
        self.run_cmd("clear", self.proj, "-s", "bbb22222", "--yes", "--plain")
        self.assertFalse(os.path.exists(bak))

    def test_the_projects_memory_is_left_alone(self):
        mem = os.path.join(self.ph, "work", "projects", self.enc, "memory")
        os.makedirs(mem, exist_ok=True)
        with open(os.path.join(mem, "MEMORY.md"), "w") as fh:
            fh.write("- [a](a.md)\n")
        self.run_cmd("clear", self.proj, "--all", "--yes", "--plain")
        self.assertTrue(os.path.isfile(os.path.join(mem, "MEMORY.md")),
                        "memory is shared by the project, not owned by one session")

    def test_another_projects_sessions_are_left_alone(self):
        other = os.path.join(self.home, "code", "other")
        os.makedirs(other, exist_ok=True)
        keep = os.path.join(self.ph, "work", "projects", encode_dir(other),
                            "ddd44444-0000-0000-0000-000000000000.jsonl")
        transcript(keep, other, ["different project"])
        self.run_cmd("clear", self.proj, "--all", "--yes", "--plain")
        self.assertTrue(os.path.isfile(keep))

    def test_the_freed_size_is_reported(self):
        _, out, _ = self.run_cmd("clear", self.proj, "--all", "--yes", "--plain")
        self.assertIn("freed", out)

    def test_the_path_can_be_typed_in_another_case(self):
        # Windows and macOS treat Proj and proj as one directory. On a
        # case-sensitive filesystem they are two, and then finding nothing is
        # the correct answer.
        _, out, _ = self.run_cmd("clear", self.proj.upper(), "--dry-run",
                                 "--all", "--plain")
        if os.path.isdir(self.proj.upper()):
            self.assertIn("aaa11111", out, "same directory, different case")
        else:
            self.assertIn("no such path", out + " no such path")

    def test_a_trailing_separator_is_the_same_directory(self):
        _, out, _ = self.run_cmd("clear", self.proj + os.sep, "--dry-run",
                                 "--all", "--plain")
        self.assertIn("aaa11111", out)

    def test_a_relative_path_resolves(self):
        here = os.getcwd()
        try:
            os.chdir(os.path.dirname(self.proj))
            _, out, _ = self.run_cmd("clear", os.path.basename(self.proj),
                                     "--dry-run", "--all", "--plain")
        finally:
            os.chdir(here)
        self.assertIn("aaa11111", out)

    def test_no_path_means_the_current_directory(self):
        here = os.getcwd()
        try:
            os.chdir(self.proj)
            _, out, _ = self.run_cmd("clear", "--dry-run", "--all", "--plain")
        finally:
            os.chdir(here)
        self.assertIn("aaa11111", out)

    def test_is_under_only_matches_real_descendants(self):
        self.assertTrue(self.core.is_under(self.sub, self.proj))
        self.assertFalse(self.core.is_under(self.proj, self.sub))
        self.assertFalse(self.core.is_under(self.proj, self.proj))
        sibling = os.path.join(self.home, "code", "api-extra")
        os.makedirs(sibling, exist_ok=True)
        self.assertFalse(self.core.is_under(sibling, self.proj),
                         "a name that merely starts the same is not inside")

    def test_a_sibling_with_a_prefix_name_is_not_cleared(self):
        sibling = os.path.join(self.home, "code", "api-extra")
        os.makedirs(sibling, exist_ok=True)
        keep = os.path.join(self.ph, "work", "projects", encode_dir(sibling),
                            "eee55555-0000-0000-0000-000000000000.jsonl")
        transcript(keep, sibling, ["a different project"])
        self.run_cmd("clear", self.proj, "-r", "--all", "--yes", "--plain")
        self.assertTrue(os.path.isfile(keep))

    def test_session_parts_finds_all_three(self):
        side = self.side_of(self.w_file)
        with open(self.w_file + ".bak", "w") as fh:
            fh.write("{}\n")
        parts = self.core.session_parts(self.w_file)
        self.assertEqual(sorted(parts), sorted([self.w_file, self.w_file + ".bak", side]))


class TestPruneOrphaned(Fixture):
    """A session whose project directory is gone cannot be usefully resumed,
    but it still holds everything that was said there."""

    def setUp(self):
        super().setUp()
        self.here = os.path.join(self.home, "code", "here")
        self.gone = os.path.join(self.home, "code", "gone")
        os.makedirs(self.here, exist_ok=True)
        os.makedirs(self.gone, exist_ok=True)
        self.wdir = os.path.join(self.ph, "work")
        self.live = os.path.join(self.wdir, "projects", encode_dir(self.here),
                                 "aaa11111-0000-0000-0000-000000000000.jsonl")
        self.dead = os.path.join(self.wdir, "projects", encode_dir(self.gone),
                                 "bbb22222-0000-0000-0000-000000000000.jsonl")
        transcript(self.live, self.here, ["still working here"])
        transcript(self.dead, self.gone, ["project since deleted"])
        shutil.rmtree(self.gone)

    def test_the_orphan_is_detected(self):
        found = [os.path.basename(f) for f, _, _ in
                 self.core.orphaned_sessions("work")]
        self.assertEqual(found, [os.path.basename(self.dead)])

    def test_a_plain_prune_ignores_it(self):
        code, out, _ = self.run_cmd("prune", "-o", "3650", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(self.dead), "age alone must not take it")

    def test_orphaned_lists_it(self):
        code, out, _ = self.run_cmd("prune", "--orphaned", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("bbb22222", out)
        self.assertNotIn("aaa11111", out)

    def test_orphaned_is_a_dry_run_without_yes(self):
        self.run_cmd("prune", "--orphaned", "--plain")
        self.assertTrue(os.path.isfile(self.dead))

    def test_orphaned_deletes_it_with_yes(self):
        code, _, _ = self.run_cmd("prune", "--orphaned", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.dead))
        self.assertTrue(os.path.isfile(self.live), "a live project is untouched")

    def test_orphaned_alone_does_not_sweep_by_age(self):
        long_ago = time.time() - 400 * 86400
        os.utime(self.live, (long_ago, long_ago))
        self.run_cmd("prune", "--orphaned", "--yes", "--plain")
        self.assertTrue(os.path.isfile(self.live),
                        "--orphaned must not imply the age default")

    def test_age_and_orphaned_combine(self):
        long_ago = time.time() - 400 * 86400
        os.utime(self.live, (long_ago, long_ago))
        code, out, _ = self.run_cmd("prune", "-o", "90", "--orphaned", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("aaa11111", out)
        self.assertIn("bbb22222", out)
        self.assertIn("WHY", out, "two reasons means the column is shown")

    def test_a_session_counted_once_when_both_reasons_apply(self):
        long_ago = time.time() - 400 * 86400
        os.utime(self.dead, (long_ago, long_ago))
        _, out, _ = self.run_cmd("prune", "-o", "90", "--orphaned", "--plain")
        self.assertEqual(out.count("bbb22222"), 1)

    def test_an_unreadable_transcript_is_not_called_an_orphan(self):
        junk = os.path.join(self.wdir, "projects", encode_dir(self.here),
                            "ccc33333-0000-0000-0000-000000000000.jsonl")
        with open(junk, "w") as fh:
            fh.write("not json\n")
        self.run_cmd("prune", "--orphaned", "--yes", "--plain")
        self.assertTrue(os.path.isfile(junk), "no recorded directory, no verdict")


class TestPruneTakesEverything(Fixture):
    """prune used to remove the transcript and leave the rest on disk."""

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        self.enc = encode_dir(self.proj)
        self.wdir = os.path.join(self.ph, "work")
        self.sid = "aaa11111-0000-0000-0000-000000000000"
        self.keep = "bbb22222-0000-0000-0000-000000000000"
        self.f = os.path.join(self.wdir, "projects", self.enc, self.sid + ".jsonl")
        transcript(self.f, self.proj, ["old work"])
        transcript(os.path.join(self.wdir, "projects", self.enc,
                                self.keep + ".jsonl"), self.proj, ["recent"])
        long_ago = time.time() - 400 * 86400
        os.utime(self.f, (long_ago, long_ago))
        self.side = os.path.join(self.wdir, "projects", self.enc, self.sid,
                                 "tool-results", "r1.txt")
        self.hist = os.path.join(self.wdir, "file-history", self.sid, "v1")
        self.keep_hist = os.path.join(self.wdir, "file-history", self.keep, "v1")
        for path in (self.side, self.hist, self.keep_hist):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write("x" * 4000)

    def test_the_side_files_go_too(self):
        code, _, _ = self.run_cmd("prune", "-o", "90", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(self.side))

    def test_the_file_history_goes_too(self):
        self.run_cmd("prune", "-o", "90", "--yes", "--plain")
        self.assertFalse(os.path.exists(self.hist),
                         "it holds copies of the files that session edited")

    def test_a_newer_sessions_files_are_untouched(self):
        self.run_cmd("prune", "-o", "90", "--yes", "--plain")
        self.assertTrue(os.path.isfile(self.keep_hist))
        self.assertTrue(os.path.isfile(os.path.join(
            self.wdir, "projects", self.enc, self.keep + ".jsonl")))

    def test_the_size_counts_everything_it_removes(self):
        _, out, _ = self.run_cmd("prune", "-o", "90", "--plain")
        self.assertIn("KB", out, "the transcript alone is a few hundred bytes")

    def test_doctor_finds_nothing_stranded_afterwards(self):
        self.run_cmd("prune", "-o", "90", "--yes", "--plain")
        _, out, _ = self.run_cmd("doctor")
        self.assertIn("nothing is left over", out)


class TestPrune(Fixture):
    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        enc = encode_dir(self.proj)
        self.old = os.path.join(self.home, ".claude", "projects", enc,
                                "eee11111-0000-0000-0000-000000000000.jsonl")
        self.new = os.path.join(self.home, ".claude", "projects", enc,
                                "fff22222-0000-0000-0000-000000000000.jsonl")
        transcript(self.old, self.proj, ["ancient history"])
        transcript(self.new, self.proj, ["recent work"])
        long_ago = time.time() - 200 * 86400
        os.utime(self.old, (long_ago, long_ago))

    def test_dry_run_deletes_nothing(self):
        code, out, _ = self.run_cmd("prune", "-o", "90", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertTrue(os.path.isfile(self.old))

    def test_yes_deletes_only_the_old_one(self):
        code, out, _ = self.run_cmd("prune", "-o", "90", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.isfile(self.old))
        self.assertTrue(os.path.isfile(self.new), "recent sessions must survive")

    def test_nothing_old_enough_is_a_no_op(self):
        code, out, _ = self.run_cmd("prune", "-o", "3650", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("nothing older", out)
        self.assertTrue(os.path.isfile(self.old))

    def test_can_target_one_profile(self):
        code, out, _ = self.run_cmd("prune", "-o", "90", "-p", "work", "--plain")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(self.old), "other profiles must be untouched")


class TestBest(Fixture):
    def test_picks_the_profile_with_the_most_headroom(self):
        w = os.path.join(self.ph, "work")
        with open(os.path.join(w, ".claude.json"), "w") as fh:
            json.dump({"oauthAccount": {"emailAddress": "me@work.com"},
                       "cachedUsageUtilization": {
                           "fetchedAtMs": int(time.time() * 1000),
                           "utilization": {"five_hour": {"utilization": 5, "resets_at": None},
                                           "seven_day": {"utilization": 5, "resets_at": None}}}}, fh)
        code, out, _ = self.run_cmd("best", "--cached", "--quiet")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "work")      # work 5% beats default 59%

    def test_judged_by_the_tightest_limit(self):
        w = os.path.join(self.ph, "work")
        with open(os.path.join(w, ".claude.json"), "w") as fh:
            json.dump({"oauthAccount": {"emailAddress": "me@work.com"},
                       "cachedUsageUtilization": {
                           "fetchedAtMs": int(time.time() * 1000),
                           "utilization": {"five_hour": {"utilization": 1, "resets_at": None},
                                           "seven_day": {"utilization": 95, "resets_at": None}}}}, fh)
        code, out, _ = self.run_cmd("best", "--cached", "--quiet")
        self.assertEqual(out.strip(), "default",
                         "a profile at 95% weekly is not 'free' just because its 5h is 1%")

    def test_no_usable_profiles_exits_one(self):
        os.remove(os.path.join(self.home, ".claude.json"))
        shutil.rmtree(os.path.join(self.ph, "work"))
        code, _, err = self.run_cmd("best", "--cached", "--quiet")
        self.assertEqual(code, 1)
        self.assertIn("no signed-in profile", err)


class TestUpdate(Fixture):
    def test_version_comparison(self):
        v = self.core._vtuple
        self.assertGreater(v("1.2.0"), v("1.1.9"))
        self.assertGreater(v("2.0.0"), v("1.99.99"))
        self.assertEqual(v("1.1.0"), v("1.1.0"))
        self.assertGreater(v("v1.1.0".lstrip("v")), v("1.0.9"))

    def test_version_comparison_survives_junk(self):
        self.assertEqual(self.core._vtuple("not-a-version"), (0,))

    def test_installed_version_includes_the_number(self):
        self.assertIn(self.core.__version__, self.core.installed_version())

    def test_check_does_not_modify_anything(self):
        before = sorted(os.listdir(self.ph))
        code, _, _ = self.run_cmd("update", "--check")
        self.assertIn(code, (0, 1))            # 1 if GitHub is unreachable
        self.assertEqual(sorted(os.listdir(self.ph)), before)


class TestBestRobustness(Fixture):
    def test_survives_a_profile_reporting_only_one_limit(self):
        w = os.path.join(self.ph, "work")
        with open(os.path.join(w, ".claude.json"), "w") as fh:
            json.dump({"oauthAccount": {"emailAddress": "me@work.com"},
                       "cachedUsageUtilization": {
                           "fetchedAtMs": int(time.time() * 1000),
                           "utilization": {"five_hour": {"utilization": 12.0, "resets_at": None},
                                           "seven_day": None}}}, fh)
        code, out, err = self.run_cmd("best", "--cached")
        self.assertEqual(code, 0, f"crashed: {err}")
        self.assertIn("work", out)

    def test_until_handles_a_z_suffix(self):
        # datetime.fromisoformat cannot parse 'Z' before Python 3.11
        self.assertNotEqual(self.core.until("2099-01-01T00:00:00Z"), "-")

    def test_until_handles_junk(self):
        self.assertEqual(self.core.until("not a date"), "-")
        self.assertEqual(self.core.until(None), "-")


class TestStatusline(Fixture):
    def payload(self):
        return json.dumps({
            "model": {"display_name": "Opus 5"},
            "workspace": {"current_dir": "/home/u/p"},
            "context_window": {"used_percentage": 52, "context_window_size": 1000000},
            "rate_limits": {"five_hour": {"used_percentage": 2},
                            "seven_day": {"used_percentage": 3}},
            "cost": {"total_cost_usd": 1.23},
        })

    def render(self, show):
        import io as _io
        out = _io.StringIO()
        old_in, old_argv = sys.stdin, sys.argv
        sys.stdin = _io.StringIO(self.payload())
        sys.argv = ["claude-profiles", "statusline", "--show", show]
        try:
            with redirect_stdout(out):
                self.core.main()
        finally:
            sys.stdin, sys.argv = old_in, old_argv
        return out.getvalue()

    def test_shows_the_profile(self):
        self.assertIn("default", self.render("profile"))

    def test_limits_come_from_the_payload(self):
        r = self.render("limits")
        self.assertIn("5h 2%", r)
        self.assertIn("7d 3%", r)

    def test_context_and_cost(self):
        r = self.render("context,cost")
        self.assertIn("ctx 52%", r)
        self.assertIn("$1.23", r)

    def test_unknown_segment_is_ignored(self):
        self.assertNotIn("nonsense", self.render("profile,nonsense"))

    def test_install_writes_the_setting(self):
        err = self.core.install_statusline("work", "profile,limits")
        self.assertIsNone(err)
        with open(os.path.join(self.ph, "work", "settings.json")) as fh:
            cfg = json.load(fh)
        self.assertIn("statusline", cfg["statusLine"]["command"])

    def test_install_refuses_an_unknown_profile(self):
        self.assertIn("no such profile", self.core.install_statusline("nope", "profile"))

    def test_install_leaves_a_foreign_statusline_alone(self):
        f = os.path.join(self.ph, "work", "settings.json")
        with open(f, "w") as fh:
            json.dump({"statusLine": {"type": "command", "command": "my-own-thing"}}, fh)
        err = self.core.install_statusline("work", "profile")
        self.assertIn("already has a different statusLine", err)
        with open(f) as fh:
            self.assertEqual(json.load(fh)["statusLine"]["command"], "my-own-thing")

    def test_force_replaces_it(self):
        f = os.path.join(self.ph, "work", "settings.json")
        with open(f, "w") as fh:
            json.dump({"statusLine": {"type": "command", "command": "my-own-thing"}}, fh)
        self.assertIsNone(self.core.install_statusline("work", "profile", force=True))
        with open(f) as fh:
            self.assertIn("statusline", json.load(fh)["statusLine"]["command"])


class TestUpstreamChecks(Fixture):
    """These guard the two Claude Code internals this tool depends on."""

    def write(self, *lines):
        d = os.path.join(self.home, ".claude", "projects", "-x")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "up11111-0000-0000-0000-000000000000.jsonl")
        with open(p, "w") as fh:
            for o in lines:
                fh.write(json.dumps(o) + "\n")
        return p

    def test_current_format_passes(self):
        self.write({"type": "user", "cwd": "/x", "message": {"content": "hi"}})
        ok, detail = self.core.check_transcript_format()
        self.assertTrue(ok, detail)

    def test_a_renamed_field_is_caught(self):
        self.write({"type": "user", "cwd": "/x", "payload": {"content": "hi"}})
        ok, detail = self.core.check_transcript_format()
        self.assertFalse(ok)
        self.assertIn("message", detail)

    def test_unreadable_user_messages_are_caught(self):
        self.write({"type": "assistant", "cwd": "/x", "message": {"content": "hi"}})
        ok, detail = self.core.check_transcript_format()
        self.assertFalse(ok)
        self.assertIn("no user messages", detail)

    def test_no_transcripts_is_not_a_failure(self):
        ok, detail = self.core.check_transcript_format()
        self.assertIsNone(ok)

    def test_missing_usage_fields_are_caught(self):
        self.core.fetch_live = lambda pdir, timeout=6: (None, "no usage in response")
        ok, detail = self.core.check_usage_endpoint()
        self.assertFalse(ok)
        self.assertIn("no longer has the fields", detail)

    def test_a_transient_failure_is_not_reported_as_a_breakage(self):
        for why in ("rate limited", "unreachable", "token expired"):
            self.core.fetch_live = lambda pdir, timeout=6, w=why: (None, w)
            ok, detail = self.core.check_usage_endpoint()
            self.assertIsNone(ok, f"{why} should warn, not fail")

    def test_a_good_response_passes(self):
        self.core.fetch_live = lambda pdir, timeout=6: (
            {"5h": {"pct": 1}, "7d": {"pct": 2}, "age": 0, "live": True}, "")
        ok, detail = self.core.check_usage_endpoint()
        self.assertTrue(ok, detail)

    def test_doctor_does_not_check_upstream_unless_asked(self):
        code, out, _ = self.run_cmd("doctor")
        self.assertNotIn("claude code integration", out)


class TestStrandedSideFiles(Fixture):
    """Handoffs made before 2.1.0 left the <sid>/ directory in the source
    profile. doctor has to point at them."""

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        self.enc = encode_dir(self.proj)
        self.pdir = os.path.join(self.ph, "work", "projects", self.enc)
        self.sid = "aaa11111-0000-0000-0000-000000000000"

    def side(self, sid):
        path = os.path.join(self.pdir, sid, "tool-results", "r1.txt")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("x" * 100)

    def test_a_directory_without_its_transcript_is_reported(self):
        self.side(self.sid)
        code, out, _ = self.run_cmd("doctor")
        self.assertIn("stranded session files", out)
        self.assertIn("aaa11111", out)

    def test_one_that_sits_with_its_transcript_is_not_reported(self):
        self.side(self.sid)
        transcript(os.path.join(self.pdir, self.sid + ".jsonl"), self.proj, ["hi"])
        _, out, _ = self.run_cmd("doctor")
        self.assertNotIn("aaa11111", out)
        self.assertIn("nothing is left over", out)

    def test_memory_is_not_mistaken_for_a_session_directory(self):
        mem = os.path.join(self.pdir, "memory")
        os.makedirs(mem, exist_ok=True)
        with open(os.path.join(mem, "MEMORY.md"), "w") as fh:
            fh.write("- [a](a.md)\n")
        _, out, _ = self.run_cmd("doctor")
        self.assertIn("nothing is left over", out)

    def test_a_bak_does_not_count_as_a_live_transcript(self):
        self.side(self.sid)
        with open(os.path.join(self.pdir, self.sid + ".jsonl.bak"), "w") as fh:
            fh.write("{}\n")
        _, out, _ = self.run_cmd("doctor")
        self.assertIn("aaa11111", out)

    def test_nothing_to_report_on_an_empty_profile(self):
        _, out, _ = self.run_cmd("doctor")
        self.assertIn("nothing is left over", out)


class TestSessionTraces(Fixture):
    """Claude Code keys several profile-level folders by session id. Deleting
    only the transcript leaves that content readable, which is the whole point
    of deleting a session."""

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        self.enc = encode_dir(self.proj)
        self.sid = "aaa11111-0000-0000-0000-000000000000"
        self.other = "bbb22222-0000-0000-0000-000000000000"
        self.wdir = os.path.join(self.ph, "work")
        transcript(os.path.join(self.wdir, "projects", self.enc, self.sid + ".jsonl"),
                   self.proj, ["one"])

    def trace(self, top, name, body="secret source code"):
        path = os.path.join(self.wdir, top, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if name.endswith((".mode", ".json")):
            with open(path, "w") as fh:
                fh.write(body)
        else:
            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, "v1"), "w") as fh:
                fh.write(body)
        return path

    # ---- what counts as a trace -------------------------------------------
    def test_a_directory_named_after_the_session_is_found(self):
        hist = self.trace("file-history", self.sid)
        self.assertIn(hist, self.core.session_traces(self.wdir, self.sid))

    def test_a_file_named_after_the_session_is_found(self):
        mode = self.trace(".caveman-sessions", self.sid + ".mode", "caveman")
        self.assertIn(mode, self.core.session_traces(self.wdir, self.sid))

    def test_the_short_prefix_jobs_uses_is_found(self):
        job = self.trace("jobs", self.sid[:8])
        self.assertIn(job, self.core.session_traces(self.wdir, self.sid))

    def test_another_sessions_files_are_not_touched(self):
        mine = self.trace("file-history", self.sid)
        theirs = self.trace("file-history", self.other)
        traces = self.core.session_traces(self.wdir, self.sid)
        self.assertIn(mine, traces)
        self.assertNotIn(theirs, traces)

    def test_a_name_that_merely_contains_the_id_is_not_touched(self):
        near = self.trace("file-history", self.sid + "-copy")
        self.assertNotIn(near, self.core.session_traces(self.wdir, self.sid))

    def test_the_projects_directory_is_left_to_the_session_itself(self):
        for path in self.core.session_traces(self.wdir, self.sid):
            self.assertNotIn(os.sep + "projects" + os.sep, path)

    # ---- clearing a session takes them ------------------------------------
    def test_clear_deletes_the_traces(self):
        hist = self.trace("file-history", self.sid)
        job = self.trace("jobs", self.sid[:8])
        mode = self.trace(".caveman-sessions", self.sid + ".mode", "caveman")
        code, out, _ = self.run_cmd("clear", self.proj, "--all", "--yes", "--plain")
        self.assertEqual(code, 0)
        for path in (hist, job, mode):
            self.assertFalse(os.path.exists(path), path)

    def test_clear_names_what_each_file_held(self):
        self.trace("file-history", self.sid)
        _, out, _ = self.run_cmd("clear", self.proj, "--all", "--dry-run", "--plain")
        self.assertIn("copies of the files it edited", out)
        self.assertIn("the conversation", out)

    def test_clear_leaves_another_sessions_traces_alone(self):
        theirs = self.trace("file-history", self.other)
        self.run_cmd("clear", self.proj, "--all", "--yes", "--plain")
        self.assertTrue(os.path.exists(theirs))

    def test_the_traces_count_towards_the_size_freed(self):
        self.trace("file-history", self.sid, "x" * 5000)
        _, out, _ = self.run_cmd("clear", self.proj, "--all", "--dry-run", "--plain")
        self.assertIn("KB", out)

    # ---- sweeping ones left behind earlier --------------------------------
    def test_doctor_reports_a_trace_with_no_session(self):
        self.trace("file-history", self.other)
        _, out, _ = self.run_cmd("doctor")
        self.assertIn("named after deleted sessions", out)

    def test_doctor_is_quiet_when_the_session_is_still_there(self):
        self.trace("file-history", self.sid)
        _, out, _ = self.run_cmd("doctor")
        self.assertIn("nothing is left over", out)

    def test_traces_mode_lists_and_deletes_them(self):
        orphan = self.trace("file-history", self.other)
        code, out, _ = self.run_cmd("prune", "--traces", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("file-history", out)
        self.assertTrue(os.path.exists(orphan), "a prune is a dry run by default")
        code, out, _ = self.run_cmd("prune", "--traces", "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(orphan))

    def test_a_session_living_in_another_profile_is_not_stranded(self):
        # handing a session over moves the transcript but not these files
        moved = self.trace("file-history", self.other)
        transcript(os.path.join(self.home, ".claude", "projects", self.enc,
                                self.other + ".jsonl"), self.proj, ["moved here"])
        self.assertEqual(self.core.stranded_traces("work"), [],
                         "the session still exists, in another profile")
        self.run_cmd("prune", "--traces", "--yes", "--plain")
        self.assertTrue(os.path.exists(moved), "a resumable session lost its history")

    def test_doctor_is_quiet_about_a_session_held_in_another_profile(self):
        self.trace("file-history", self.other)
        transcript(os.path.join(self.home, ".claude", "projects", self.enc,
                                self.other + ".jsonl"), self.proj, ["moved here"])
        _, out, _ = self.run_cmd("doctor")
        self.assertIn("nothing is left over", out)

    def test_traces_mode_keeps_a_live_sessions_files(self):
        mine = self.trace("file-history", self.sid)
        self.run_cmd("prune", "--traces", "--yes", "--plain")
        self.assertTrue(os.path.exists(mine), "this session still exists")

    def test_traces_alone_does_not_sweep_by_age(self):
        old = os.path.join(self.wdir, "projects", self.enc, self.sid + ".jsonl")
        long_ago = time.time() - 400 * 86400
        os.utime(old, (long_ago, long_ago))
        self.trace("file-history", self.other)
        self.run_cmd("prune", "--traces", "--yes", "--plain")
        self.assertTrue(os.path.isfile(old), "--traces must not imply an age sweep")

    def test_traces_mode_says_so_when_there_is_nothing(self):
        code, out, _ = self.run_cmd("prune", "--traces", "--plain")
        self.assertEqual(code, 0)
        self.assertIn("nothing left over", out)

    def test_traces_mode_can_be_limited_to_one_profile(self):
        orphan = self.trace("file-history", self.other)
        code, out, _ = self.run_cmd("prune", "--traces", "-p", "empty",
                                    "--yes", "--plain")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(orphan), "a different profile was swept")


class TestHandoff(Fixture):
    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        enc = encode_dir(self.proj)
        self.enc = enc
        transcript(os.path.join(self.home, ".claude", "projects", enc, "aaa11111-0000-0000-0000-000000000000.jsonl"),
                   self.proj, ["fix the auth bug"])
        transcript(os.path.join(self.home, ".claude", "projects", enc, "aaa99999-0000-0000-0000-000000000000.jsonl"),
                   self.proj, ["another one"])

    def dest(self, sid):
        return os.path.join(self.ph, "work", "projects", self.enc, sid + ".jsonl")

    def test_copy_keeps_the_original(self):
        code, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj, "--copy")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(self.dest("aaa11111-0000-0000-0000-000000000000")))
        self.assertTrue(os.path.isfile(os.path.join(
            self.home, ".claude", "projects", self.enc,
            "aaa11111-0000-0000-0000-000000000000.jsonl")), "original must survive")

    def test_encoded_directory_name_is_preserved(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertTrue(os.path.isdir(os.path.join(self.ph, "work", "projects", self.enc)))

    def test_copy_is_byte_identical(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj, "--copy")
        src = os.path.join(self.home, ".claude", "projects", self.enc,
                           "aaa11111-0000-0000-0000-000000000000.jsonl")
        with open(src, "rb") as a, open(self.dest("aaa11111-0000-0000-0000-000000000000"), "rb") as b:
            self.assertEqual(a.read(), b.read())

    # ---- move is the default ------------------------------------------------
    def src_file(self, name="aaa11111-0000-0000-0000-000000000000.jsonl"):
        return os.path.join(self.home, ".claude", "projects", self.enc, name)

    def test_default_moves_the_session(self):
        code, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(self.dest("aaa11111-0000-0000-0000-000000000000")))
        self.assertFalse(os.path.exists(self.src_file()), "source must no longer be resumable")
        self.assertIn("moved session", out)

    def test_move_keeps_the_source_as_a_bak(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        bak = self.src_file("aaa11111-0000-0000-0000-000000000000.jsonl.bak")
        self.assertTrue(os.path.isfile(bak), "a move must be undoable")
        with open(bak, "rb") as a, open(self.dest("aaa11111-0000-0000-0000-000000000000"), "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_a_retired_session_is_gone_from_listings(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        # the other fixture session aaa99999 is still there; only aaa11111 left
        _, out, _ = self.run_cmd("sessions", "-p", "default", "-d", self.proj, "--plain")
        self.assertNotIn("aaa11111", out)
        self.assertIn("aaa99999", out)
        _, out, _ = self.run_cmd("sessions", "-p", "work", "-d", self.proj, "--plain")
        self.assertIn("aaa11111", out)

    def test_explicit_move_flag(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj, "--move")
        self.assertFalse(os.path.exists(self.src_file()))

    def test_move_and_copy_conflict(self):
        code, _, err = self.run_cmd("handoff", "work", "-d", self.proj, "--move", "--copy")
        self.assertEqual(code, 2)

    def test_env_var_makes_copy_the_default(self):
        os.environ["CLAUDE_HANDOFF_COPY"] = "1"
        try:
            self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        finally:
            os.environ.pop("CLAUDE_HANDOFF_COPY", None)
        self.assertTrue(os.path.exists(self.src_file()))

    def test_move_flag_beats_the_env_var(self):
        os.environ["CLAUDE_HANDOFF_COPY"] = "1"
        try:
            self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj, "--move")
        finally:
            os.environ.pop("CLAUDE_HANDOFF_COPY", None)
        self.assertFalse(os.path.exists(self.src_file()))

    def test_a_refused_move_leaves_the_source_alone(self):
        # target is further along - the guard refuses, and nothing may be retired
        transcript(os.path.join(self.ph, "work", "projects", self.enc,
                                "aaa11111-0000-0000-0000-000000000000.jsonl"),
                   self.proj, ["a", "b", "c", "d", "e", "f"])
        code, _, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertEqual(code, 1)
        self.assertTrue(os.path.exists(self.src_file()), "refusal must not retire the source")

    def test_dry_run_move_retires_nothing(self):
        code, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("would move", out)
        self.assertTrue(os.path.exists(self.src_file()))
        self.assertFalse(os.path.exists(self.dest("aaa11111-0000-0000-0000-000000000000")))

    def test_move_with_an_identical_target_still_retires_the_source(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj, "--copy")
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertFalse(os.path.exists(self.src_file()))
        self.assertTrue(os.path.isfile(self.dest("aaa11111-0000-0000-0000-000000000000")))

    def test_ambiguous_prefix_is_refused(self):
        code, _, err = self.run_cmd("handoff", "work", "aaa", "-d", self.proj)
        self.assertEqual(code, 1)
        self.assertIn("ambiguous", err)

    def test_unknown_target_is_refused(self):
        code, _, err = self.run_cmd("handoff", "nosuch", "-d", self.proj)
        self.assertEqual(code, 1)
        self.assertIn("no such profile", err)

    def test_same_profile_is_refused(self):
        code, _, err = self.run_cmd("handoff", "default", "-d", self.proj)
        self.assertEqual(code, 1)
        self.assertIn("same profile", err)

    def test_latest_is_chosen_when_no_id_given(self):
        newest = os.path.join(self.home, ".claude", "projects", self.enc,
                              "aaa99999-0000-0000-0000-000000000000.jsonl")
        os.utime(newest, (time.time() + 10, time.time() + 10))
        code, out, _ = self.run_cmd("handoff", "work", "-d", self.proj)
        self.assertEqual(code, 0)
        self.assertIn("aaa99999", out)


class TestHandoffSideFiles(Fixture):
    """Claude Code spills tool results and subagent logs into <sid>/ next to
    the transcript. A handoff has to take them, or the resumed session in the
    target profile loses them."""

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        self.enc = encode_dir(self.proj)
        self.sid = "aaa11111-0000-0000-0000-000000000000"
        transcript(os.path.join(self.home, ".claude", "projects", self.enc,
                                self.sid + ".jsonl"), self.proj, ["fix the auth bug"])
        self.src_side = os.path.join(self.home, ".claude", "projects",
                                     self.enc, self.sid)
        self.write(os.path.join(self.src_side, "tool-results", "r1.txt"), "big output")
        self.write(os.path.join(self.src_side, "subagents", "workflows",
                                "wf_1", "journal.jsonl"), "{}\n")

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(text)

    def dst_side(self, *parts):
        return os.path.join(self.ph, "work", "projects", self.enc, self.sid, *parts)

    def src_file(self):
        return os.path.join(self.home, ".claude", "projects", self.enc,
                            self.sid + ".jsonl")

    def test_side_files_come_along(self):
        code, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(self.dst_side("tool-results", "r1.txt")))
        self.assertTrue(os.path.isfile(self.dst_side("subagents", "workflows",
                                                     "wf_1", "journal.jsonl")))
        self.assertIn("side files", out)

    def test_contents_survive_the_trip(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        with open(self.dst_side("tool-results", "r1.txt")) as fh:
            self.assertEqual(fh.read(), "big output")

    def test_a_move_takes_the_side_directory_with_it(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertFalse(os.path.exists(self.src_side),
                         "a move must not leave side files behind")

    def test_a_copy_leaves_the_side_directory_alone(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj, "--copy")
        self.assertTrue(os.path.isfile(os.path.join(self.src_side,
                                                    "tool-results", "r1.txt")))
        self.assertTrue(os.path.isfile(self.dst_side("tool-results", "r1.txt")))

    def test_a_differing_file_keeps_the_targets_copy(self):
        self.write(self.dst_side("tool-results", "r1.txt"), "the target's own")
        code, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertEqual(code, 0)
        with open(self.dst_side("tool-results", "r1.txt")) as fh:
            self.assertEqual(fh.read(), "the target's own")
        self.assertIn("kept the target's", out)

    def test_a_differing_file_keeps_the_source_directory(self):
        self.write(self.dst_side("tool-results", "r1.txt"), "the target's own")
        _, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertTrue(os.path.isfile(os.path.join(self.src_side,
                                                    "tool-results", "r1.txt")),
                        "nothing may be dropped on a conflict")
        self.assertIn("side files stayed", out)

    def test_an_identical_file_is_not_recopied(self):
        self.write(self.dst_side("tool-results", "r1.txt"), "big output")
        _, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertIn("already there", out)
        self.assertFalse(os.path.exists(self.src_side))

    def test_dry_run_writes_no_side_files(self):
        code, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d",
                                    self.proj, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("side files: 2 to copy", out)
        self.assertFalse(os.path.exists(self.dst_side()))
        self.assertTrue(os.path.isdir(self.src_side))

    def test_a_refused_handoff_keeps_the_side_files(self):
        transcript(os.path.join(self.ph, "work", "projects", self.enc,
                                self.sid + ".jsonl"),
                   self.proj, ["a", "b", "c", "d", "e"])
        code, _, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertEqual(code, 1)
        self.assertTrue(os.path.isdir(self.src_side))

    def test_an_identical_target_still_moves_the_side_files(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj, "--copy")
        shutil.rmtree(self.dst_side())
        code, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertEqual(code, 0)
        self.assertIn("unchanged", out)
        self.assertTrue(os.path.isfile(self.dst_side("tool-results", "r1.txt")))
        self.assertFalse(os.path.exists(self.src_side))

    def test_a_session_with_no_side_files_is_fine(self):
        shutil.rmtree(self.src_side)
        code, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertEqual(code, 0)
        self.assertNotIn("side files", out)


class TestHandoffOverwrite(Fixture):
    """A session copied both ways must never silently lose turns."""

    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        self.enc = encode_dir(self.proj)
        self.sid = "ovr11111-0000-0000-0000-000000000000"

    def put(self, where, msgs):
        d = (os.path.join(self.home, ".claude", "projects", self.enc) if where == "default"
             else os.path.join(self.ph, where, "projects", self.enc))
        transcript(os.path.join(d, f"{self.sid}.jsonl"), self.proj, msgs)

    def turns(self, where):
        d = (os.path.join(self.home, ".claude", "projects", self.enc) if where == "default"
             else os.path.join(self.ph, where, "projects", self.enc))
        f = os.path.join(d, f"{self.sid}.jsonl")
        return self.core.turn_count(f) if os.path.exists(f) else 0

    def test_absent_target_is_copied(self):
        self.put("default", ["a", "b", "c"])
        code, _, _ = self.run_cmd("handoff", "work", "-d", self.proj)
        self.assertEqual(code, 0)
        self.assertEqual(self.turns("work"), 3)

    def test_identical_target_is_left_alone(self):
        self.put("default", ["a", "b"]); self.put("work", ["a", "b"])
        code, out, _ = self.run_cmd("handoff", "work", "-d", self.proj)
        self.assertEqual(code, 0)
        self.assertIn("unchanged", out)

    def test_behind_target_is_updated(self):
        self.put("default", ["a", "b", "c", "d"]); self.put("work", ["a", "b"])
        code, out, _ = self.run_cmd("handoff", "work", "-d", self.proj)
        self.assertEqual(code, 0)
        self.assertEqual(self.turns("work"), 4)
        self.assertIn("2 turns -> 4", out)

    def test_target_that_is_ahead_is_refused(self):
        self.put("default", ["a", "b"]); self.put("work", ["a", "b", "c", "d", "e"])
        code, _, err = self.run_cmd("handoff", "work", "-d", self.proj)
        self.assertEqual(code, 1)
        self.assertIn("further along", err)
        self.assertEqual(self.turns("work"), 5, "the target must not be touched")

    def test_diverged_target_is_refused(self):
        self.put("default", ["a", "b", "X"]); self.put("work", ["a", "b", "Y"])
        code, _, err = self.run_cmd("handoff", "work", "-d", self.proj)
        self.assertEqual(code, 1)
        self.assertIn("contents differ", err)

    def test_force_overwrites_and_keeps_a_backup(self):
        self.put("default", ["a", "b"]); self.put("work", ["a", "b", "c", "d", "e"])
        code, out, _ = self.run_cmd("handoff", "work", "-d", self.proj, "--force")
        self.assertEqual(code, 0)
        self.assertEqual(self.turns("work"), 2)
        bak = os.path.join(self.ph, "work", "projects", self.enc, f"{self.sid}.jsonl.bak")
        self.assertTrue(os.path.isfile(bak), "the overwritten copy must be recoverable")
        self.assertIn(".bak", out)

    def test_dry_run_reports_the_conflict_without_writing(self):
        self.put("default", ["a", "b"]); self.put("work", ["a", "b", "c"])
        code, out, err = self.run_cmd("handoff", "work", "-d", self.proj, "--dry-run")
        self.assertEqual(code, 1, "a refusal is still a refusal in dry run")
        self.assertEqual(self.turns("work"), 3)

    def test_round_trip_without_divergence_is_fine(self):
        self.put("default", ["a", "b"])
        self.run_cmd("handoff", "work", "-d", self.proj)
        self.put("work", ["a", "b", "c", "d"])            # work continues there
        os.environ["CLAUDE_CONFIG_DIR"] = os.path.join(self.ph, "work")
        try:
            code, _, _ = self.run_cmd("handoff", "default", "-d", self.proj)
        finally:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        self.assertEqual(code, 0)
        self.assertEqual(self.turns("default"), 4)


class TestHandoffMemory(Fixture):
    def setUp(self):
        super().setUp()
        self.proj = os.path.join(self.home, "code", "api")
        os.makedirs(self.proj, exist_ok=True)
        self.enc = encode_dir(self.proj)
        transcript(os.path.join(self.home, ".claude", "projects", self.enc,
                                "mem11111-0000-0000-0000-000000000000.jsonl"),
                   self.proj, ["work on this"])
        self.src_mem = os.path.join(self.home, ".claude", "projects", self.enc, "memory")
        os.makedirs(self.src_mem, exist_ok=True)
        self.write(self.src_mem, "no-em-dashes.md", "never use em dashes")
        self.write(self.src_mem, "show-drafts.md", "show drafts first")
        self.write(self.src_mem, "MEMORY.md",
                   "- [No em dashes](no-em-dashes.md)\n- [Show drafts](show-drafts.md)")

    def write(self, d, name, body):
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w") as fh:
            fh.write(body + "\n")

    def dst_mem(self):
        return os.path.join(self.ph, "work", "projects", self.enc, "memory")

    def files(self):
        d = self.dst_mem()
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def test_memory_is_not_copied_without_the_flag(self):
        self.run_cmd("handoff", "work", "-d", self.proj)
        self.assertEqual(self.files(), [])

    def test_the_output_mentions_memory_exists(self):
        _, out, _ = self.run_cmd("handoff", "work", "-d", self.proj)
        self.assertIn("--with-memory", out)

    def test_with_memory_copies_into_an_empty_target(self):
        code, _, _ = self.run_cmd("handoff", "work", "-d", self.proj, "--with-memory")
        self.assertEqual(code, 0)
        self.assertEqual(self.files(), ["MEMORY.md", "no-em-dashes.md", "show-drafts.md"])

    def test_dry_run_changes_nothing(self):
        code, out, _ = self.run_cmd("handoff", "work", "-d", self.proj,
                                    "--with-memory", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("dry run", out)
        self.assertEqual(self.files(), [])
        self.assertFalse(os.path.exists(os.path.join(
            self.ph, "work", "projects", self.enc,
            "mem11111-0000-0000-0000-000000000000.jsonl")), "the transcript too")

    def test_identical_files_are_left_alone(self):
        self.write(self.dst_mem(), "no-em-dashes.md", "never use em dashes")
        _, out, _ = self.run_cmd("handoff", "work", "-d", self.proj, "--with-memory")
        self.assertIn("already there", out)
        self.assertNotIn("no-em-dashes.from-default.md", self.files())

    def test_a_real_conflict_keeps_both(self):
        self.write(self.dst_mem(), "no-em-dashes.md", "em dashes are fine here")
        _, out, _ = self.run_cmd("handoff", "work", "-d", self.proj, "--with-memory")
        self.assertIn("side by side", out)
        self.assertIn("no-em-dashes.from-default.md", self.files())
        with open(os.path.join(self.dst_mem(), "no-em-dashes.md")) as fh:
            self.assertIn("fine here", fh.read(), "the target's version must survive")

    def test_a_conflict_is_added_to_the_index(self):
        self.write(self.dst_mem(), "no-em-dashes.md", "em dashes are fine here")
        self.write(self.dst_mem(), "MEMORY.md", "- [No em dashes](no-em-dashes.md)")
        self.run_cmd("handoff", "work", "-d", self.proj, "--with-memory")
        with open(os.path.join(self.dst_mem(), "MEMORY.md")) as fh:
            self.assertIn("no-em-dashes.from-default.md", fh.read())

    def test_the_index_is_a_union_not_a_replacement(self):
        self.write(self.dst_mem(), "local-only.md", "something the target knew")
        self.write(self.dst_mem(), "MEMORY.md", "- [Local only](local-only.md)")
        self.run_cmd("handoff", "work", "-d", self.proj, "--with-memory")
        with open(os.path.join(self.dst_mem(), "MEMORY.md")) as fh:
            body = fh.read()
        self.assertIn("local-only.md", body, "the target's own entry must survive")
        self.assertIn("show-drafts.md", body, "and the incoming ones are added")

    def test_force_memory_replaces(self):
        self.write(self.dst_mem(), "local-only.md", "gone after --force-memory")
        self.run_cmd("handoff", "work", "-d", self.proj, "--force-memory")
        self.assertNotIn("local-only.md", self.files())

    def test_no_memory_to_copy_is_not_an_error(self):
        shutil.rmtree(self.src_mem)
        code, out, _ = self.run_cmd("handoff", "work", "-d", self.proj, "--with-memory")
        self.assertEqual(code, 0)
        self.assertIn("no memory saved", out)


class TestRemove(Fixture):
    def test_refuses_default(self):
        code, _, err = self.run_cmd("remove", "default", "--yes")
        self.assertEqual(code, 1)
        self.assertIn("refusing", err)

    def test_refuses_unknown(self):
        code, _, err = self.run_cmd("remove", "nosuch", "--yes")
        self.assertEqual(code, 1)
        self.assertIn("no such profile", err)

    def test_removes_the_directory(self):
        code, _, _ = self.run_cmd("remove", "empty", "--yes")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.isdir(os.path.join(self.ph, "empty")))

    def test_other_profiles_survive(self):
        self.run_cmd("remove", "empty", "--yes")
        self.assertTrue(os.path.isdir(os.path.join(self.ph, "work")))


class TestClone(Fixture):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.ph, "work", "settings.json"), "w") as fh:
            fh.write('{"theme":"dark"}')
        os.makedirs(os.path.join(self.ph, "work", "plugins", "thing"), exist_ok=True)
        os.makedirs(os.path.join(self.ph, "work", "projects", "junk"), exist_ok=True)

    def test_copies_settings_and_plugins(self):
        code, _, _ = self.run_cmd("clone", "work", "empty")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.ph, "empty", "settings.json")))
        self.assertTrue(os.path.isdir(os.path.join(self.ph, "empty", "plugins", "thing")))

    def test_never_copies_credentials(self):
        self.run_cmd("clone", "work", "empty")
        self.assertFalse(os.path.exists(os.path.join(self.ph, "empty", ".credentials.json")))

    def test_never_copies_history(self):
        self.run_cmd("clone", "work", "empty")
        self.assertFalse(os.path.exists(os.path.join(self.ph, "empty", "projects")))

    def test_refuses_to_clone_over_default(self):
        code, _, err = self.run_cmd("clone", "work", "default")
        self.assertEqual(code, 1)
        self.assertIn("refusing", err)

    def test_existing_files_are_left_alone_without_force(self):
        os.makedirs(os.path.join(self.ph, "empty"), exist_ok=True)
        with open(os.path.join(self.ph, "empty", "settings.json"), "w") as fh:
            fh.write("MINE")
        self.run_cmd("clone", "work", "empty")
        with open(os.path.join(self.ph, "empty", "settings.json")) as fh:
            self.assertEqual(fh.read(), "MINE")

    def test_force_overwrites(self):
        with open(os.path.join(self.ph, "empty", "settings.json"), "w") as fh:
            fh.write("MINE")
        self.run_cmd("clone", "work", "empty", "--force")
        with open(os.path.join(self.ph, "empty", "settings.json")) as fh:
            self.assertIn("dark", fh.read())

    def test_unknown_source_is_refused(self):
        code, _, err = self.run_cmd("clone", "nosuch", "empty")
        self.assertEqual(code, 1)
        self.assertIn("no such profile", err)


class TestStatusOutput(Fixture):
    def test_shows_every_profile_and_its_account(self):
        code, out, _ = self.run_cmd("status", "--plain")
        self.assertEqual(code, 0)
        for expect in ("default", "work", "empty", "me@example.com", "me@work.com"):
            self.assertIn(expect, out)

    def test_marks_the_active_profile(self):
        code, out, _ = self.run_cmd("status", "--plain")
        self.assertRegex(out, r"\*\s+default")

    def test_usage_columns_render(self):
        code, out, _ = self.run_cmd("status", "--plain")
        self.assertIn("59%", out)
        self.assertIn("40%", out)

    def test_no_usage_hides_them(self):
        code, out, _ = self.run_cmd("status", "--plain", "--no-usage")
        self.assertNotIn("59%", out)

    def test_never_used_profile_is_labelled(self):
        code, out, _ = self.run_cmd("status", "--plain")
        self.assertIn("never used", out)

    def test_path_subcommand(self):
        code, out, _ = self.run_cmd("path", "work")
        self.assertEqual(out.strip(), os.path.join(self.ph, "work"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
