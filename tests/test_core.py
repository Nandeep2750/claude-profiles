#!/usr/bin/env python3
"""Tests for the claude-profiles core.

Every test runs against a throwaway HOME built from fixtures, so nothing
touches the real profiles or Keychain.
"""
import importlib.util
import io
import json
import os
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

    def test_copies_the_transcript_and_keeps_the_original(self):
        code, out, _ = self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(self.dest("aaa11111-0000-0000-0000-000000000000")))
        self.assertTrue(os.path.isfile(os.path.join(
            self.home, ".claude", "projects", self.enc,
            "aaa11111-0000-0000-0000-000000000000.jsonl")), "original must survive")

    def test_encoded_directory_name_is_preserved(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        self.assertTrue(os.path.isdir(os.path.join(self.ph, "work", "projects", self.enc)))

    def test_copy_is_byte_identical(self):
        self.run_cmd("handoff", "work", "aaa11111", "-d", self.proj)
        src = os.path.join(self.home, ".claude", "projects", self.enc,
                           "aaa11111-0000-0000-0000-000000000000.jsonl")
        with open(src, "rb") as a, open(self.dest("aaa11111-0000-0000-0000-000000000000"), "rb") as b:
            self.assertEqual(a.read(), b.read())

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
