#!/usr/bin/env python3
"""
Cross-platform core for Claude Code multi-account profiles.

This file is the tooling (safe to commit). Account data lives separately in
CLAUDE_PROFILE_HOME (default ~/.claude-profiles) and must never be committed.

Each profile is a CLAUDE_CONFIG_DIR. Claude Code derives a distinct credential
slot from that path, so profiles stay logged in simultaneously:
  macOS          -> Keychain service "Claude Code-credentials-<sha256(dir)[:8]>"
  Linux/Windows  -> <profile dir>/.credentials.json

Subcommands: path | status | sessions | handoff | remove
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

__version__ = "1.7.0"

HOME = os.path.expanduser("~")
PROF_HOME = os.environ.get("CLAUDE_PROFILE_HOME", os.path.join(HOME, ".claude-profiles"))
DEFAULT_DIR = os.path.join(HOME, ".claude")
IS_MAC = sys.platform == "darwin"
IS_WINDOWS = os.name == "nt"


def reload_hint():
    """How to reload the shell, in terms that work on this platform."""
    if IS_WINDOWS:
        return ('re-import the module or open a new PowerShell window:\n'
                '    Import-Module "$HOME\\.claude-tools\\shell\\ClaudeProfiles.psm1" -Force')
    return "run 'exec $SHELL -l' or open a new terminal"


VALID_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class BadProfileName(ValueError):
    pass


def check_name(name):
    """Reject anything that could escape CLAUDE_PROFILE_HOME.

    Profile names become directory names, and commands like `remove` delete
    what they resolve to, so a name such as '../Documents' must never be
    accepted.
    """
    if not name or not VALID_NAME.match(name) or ".." in name:
        raise BadProfileName(
            f"invalid profile name: {name!r}\n"
            "names may contain letters, digits, '.', '-' and '_', "
            "and must start with a letter or digit")
    return name


def profile_dir(name):
    if name == "default":
        return DEFAULT_DIR
    check_name(name)
    resolved = os.path.realpath(os.path.join(PROF_HOME, name))
    root = os.path.realpath(PROF_HOME)
    if resolved != root and not resolved.startswith(root + os.sep):
        raise BadProfileName(f"profile {name!r} would resolve outside {PROF_HOME}")
    return os.path.join(PROF_HOME, name)


def profile_names():
    out = ["default"]
    if os.path.isdir(PROF_HOME):
        out += sorted(d for d in os.listdir(PROF_HOME)
                      if not d.startswith(".") and os.path.isdir(os.path.join(PROF_HOME, d)))
    return out


def active_profile():
    cd = os.environ.get("CLAUDE_CONFIG_DIR")
    if not cd:
        return "default"
    cd = os.path.normpath(cd)
    if cd == os.path.normpath(DEFAULT_DIR):
        return "default"
    return os.path.basename(cd)


def keychain_service(pdir):
    if os.path.normpath(pdir) == os.path.normpath(DEFAULT_DIR):
        return "Claude Code-credentials"
    h = hashlib.sha256(pdir.encode()).hexdigest()[:8]
    return f"Claude Code-credentials-{h}"


def has_credentials(pdir):
    """True if this profile is logged in. Handles both storage backends."""
    if os.path.isfile(os.path.join(pdir, ".credentials.json")):
        return True
    if IS_MAC:
        try:
            r = subprocess.run(
                ["security", "find-generic-password",
                 "-a", os.environ.get("USER", ""), "-s", keychain_service(pdir)],
                capture_output=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False
    return False


def global_config(pdir):
    """.claude.json lives beside the config dir for default, inside it otherwise."""
    if os.path.normpath(pdir) == os.path.normpath(DEFAULT_DIR):
        return os.path.join(HOME, ".claude.json")
    return os.path.join(pdir, ".claude.json")


def account_email(pdir):
    try:
        with open(global_config(pdir)) as fh:
            return (json.load(fh).get("oauthAccount") or {}).get("emailAddress") or None
    except Exception:
        return None


OWN_CACHE = ".usage-cache.json"


def _own_cache_path(pdir):
    return os.path.join(pdir, OWN_CACHE)


def save_usage(pdir, buckets):
    """Persist a live fetch beside the profile, so plain runs see it too.

    Written to our own file rather than Claude Code's .claude.json: that file
    is Claude Code's to manage, and writing it while a session is running risks
    clobbering its state.
    """
    try:
        os.makedirs(pdir, exist_ok=True)
        payload = {"fetchedAtMs": int(time.time() * 1000),
                   "utilization": {k: buckets.get(k) for k in ("5h", "7d")}}
        tmp = _own_cache_path(pdir) + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(payload, fh)
        os.replace(tmp, _own_cache_path(pdir))
    except OSError:
        pass


def _own_cache(pdir):
    try:
        with open(_own_cache_path(pdir)) as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    u = d.get("utilization")
    if not isinstance(u, dict):
        return None
    out = {"age": max(0.0, time.time() - d.get("fetchedAtMs", 0) / 1000)}
    for k in ("5h", "7d"):
        out[k] = u.get(k) if isinstance(u.get(k), dict) else None
    return out if any(out.get(k) for k in ("5h", "7d")) else None


def usage_of(pdir):
    """Newest cached usage for a profile, or None.

    Two caches exist: Claude Code's own, refreshed only while that profile
    runs, and ours, written by --live. Whichever is newer wins.
    """
    mine = _own_cache(pdir)
    theirs = _claude_code_cache(pdir)
    if mine and theirs:
        return mine if mine["age"] <= theirs["age"] else theirs
    return mine or theirs


def _claude_code_cache(pdir):
    """Claude Code's own cachedUsageUtilization, or None."""
    try:
        with open(global_config(pdir)) as fh:
            u = json.load(fh).get("cachedUsageUtilization")
    except Exception:
        return None
    if not u or not isinstance(u.get("utilization"), dict):
        return None
    out = {"age": max(0.0, time.time() - u.get("fetchedAtMs", 0) / 1000)}
    for key, short in (("five_hour", "5h"), ("seven_day", "7d")):
        v = u["utilization"].get(key)
        if not isinstance(v, dict):
            out[short] = None
            continue
        out[short] = {"pct": v.get("utilization"),
                      "resets": v.get("resets_at"),
                      "locked": v.get("locked_reason")}
    return out


USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
REPO = "Nandeep2750/claude-profiles"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _credentials_blob(pdir):
    """The stored credential JSON for a profile, or None."""
    blob = None
    f = os.path.join(pdir, ".credentials.json")
    if os.path.isfile(f):
        try:
            with open(f) as fh:
                blob = json.load(fh)
        except Exception:
            blob = None
    if blob is None and IS_MAC:
        try:
            r = subprocess.run(["security", "find-generic-password", "-a",
                                os.environ.get("USER", ""), "-w",
                                "-s", keychain_service(pdir)],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                blob = json.loads(r.stdout.strip())
        except Exception:
            return None
    return blob if isinstance(blob, dict) else None


def access_token(pdir):
    """This profile's OAuth access token, from whichever backend holds it."""
    blob = _credentials_blob(pdir)
    return ((blob or {}).get("claudeAiOauth") or {}).get("accessToken")


def _buckets(obj):
    """Pull five_hour / seven_day out of a usage payload, shape-tolerantly."""
    u = obj.get("utilization") if isinstance(obj.get("utilization"), dict) else obj
    out = {}
    if isinstance(u, dict):
        for key, short in (("five_hour", "5h"), ("seven_day", "7d")):
            v = u.get(key)
            out[short] = ({"pct": v.get("utilization"), "resets": v.get("resets_at"),
                           "locked": v.get("locked_reason")}
                          if isinstance(v, dict) else None)
    # fall back to the flat `limits` list if the named keys are absent
    if not any(out.get(k) for k in ("5h", "7d")):
        limits = (u.get("limits") if isinstance(u, dict) else None) \
            or (obj.get("limits") if isinstance(obj, dict) else None)
        for lim in limits or []:
            if not isinstance(lim, dict):
                continue
            g = str(lim.get("group") or lim.get("kind") or "").lower()
            short = "5h" if g in ("session", "five_hour") else ("7d" if "week" in g or "seven" in g else None)
            if short and not out.get(short):
                out[short] = {"pct": lim.get("percent"), "resets": lim.get("resets_at"),
                              "locked": lim.get("locked_reason")}
    return out


def token_expiry(pdir):
    """When this profile's access token expires, as a unix time, or None."""
    blob = _credentials_blob(pdir)
    ms = ((blob or {}).get("claudeAiOauth") or {}).get("expiresAt")
    return ms / 1000 if isinstance(ms, (int, float)) else None


def fetch_live(pdir, timeout=6):
    """(usage, reason) from the API. usage is None on failure; reason says why.

    Access tokens are short-lived and Claude Code refreshes them when it runs.
    This tool deliberately does not refresh them: the refresh token may rotate,
    and writing a new one back could desynchronise Claude Code's own copy. An
    expired token is reported instead, so the fix is obvious.
    """
    token = access_token(pdir)
    if not token:
        return None, "not logged in"
    assert USAGE_URL.startswith("https://")   # noqa: S101 - guards urlopen below
    req = urllib.request.Request(USAGE_URL, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "claude-profiles",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return None, "token expired"
        if e.code == 429:
            return None, "rate limited"
        return None, f"http {e.code}"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, "unreachable"
    except (ValueError, json.JSONDecodeError):
        return None, "bad response"
    b = _buckets(payload if isinstance(payload, dict) else {})
    if not any(b.get(k) for k in ("5h", "7d")):
        return None, "no usage in response"
    b["age"] = 0.0
    b["live"] = True
    save_usage(pdir, b)
    return b, ""


def until(iso):
    """'in 54m' / 'in 1h 14m' / 'in 4d 23h' for an ISO timestamp, or '-'."""
    if not iso:
        return "-"
    try:
        dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    d = (dt - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if d <= 0:
        return "due"
    if d < 3600:
        return f"in {int(d//60)}m"
    if d < 86400:
        return f"in {int(d//3600)}h {int(d%3600//60):02d}m"
    return f"in {int(d//86400)}d {int(d%86400//3600)}h"


def ago(sec):
    if sec < 3600:
        return f"{int(sec//60)}m ago"
    if sec < 86400:
        return f"{int(sec//3600)}h ago"
    return f"{int(sec//86400)}d ago"


# ── transcripts ──────────────────────────────────────────────────────
def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "tool_result":
                    return ""
                if b.get("text"):
                    parts.append(b["text"])
        return " ".join(parts)
    return ""


def scan(path, pattern=None):
    """(cwd, branch, turns, mtime, summary) for a transcript, or None.

    With `pattern`, returns None unless some message matches, and uses the first
    matching message as the summary instead of the opening prompt.
    """
    cwd = branch = None
    turns, summary = 0, ""
    matched = None
    try:
        with open(path, errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("isSidechain"):
                    continue
                if cwd is None and o.get("cwd"):
                    cwd = o["cwd"]
                if branch is None and o.get("gitBranch"):
                    branch = o["gitBranch"]
                if pattern is not None and matched is None and o.get("type") == "assistant":
                    at = _text((o.get("message") or {}).get("content"))
                    at = " ".join(re.sub(r"<[^>]+>.*?</[^>]+>", " ", at, flags=re.S).split())
                    if at and pattern.search(at):
                        m = pattern.search(at)
                        lo = max(0, m.start() - 40)
                        matched = ("…" if lo else "") + at[lo:lo + 160]
                if o.get("type") == "user" and not o.get("isMeta"):
                    t = _text((o.get("message") or {}).get("content"))
                    t = re.sub(r"<[^>]+>.*?</[^>]+>", " ", t, flags=re.S)
                    t = " ".join(t.split())
                    if not t or t.startswith("Caveat:"):
                        continue
                    turns += 1
                    if not summary:
                        summary = t
                    if pattern is not None and matched is None and pattern.search(t):
                        matched = t
    except OSError:
        return None
    if turns == 0 and not summary:
        return None
    if pattern is not None:
        if matched is None:
            return None
        summary = matched
    return cwd, branch, turns, os.path.getmtime(path), summary


def transcripts(pname):
    root = os.path.join(profile_dir(pname), "projects")
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.endswith(".jsonl"):
                yield os.path.join(dirpath, fn)


def age(ts):
    d = time.time() - ts
    if d < 3600:    return f"{int(d//60)}m ago"
    if d < 86400:   return f"{int(d//3600)}h ago"
    if d < 7*86400: return f"{int(d//86400)}d ago"
    return time.strftime("%b %d", time.localtime(ts))


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def vlen(s):
    """Visible width, ignoring ANSI colour codes."""
    return len(ANSI_RE.sub("", s))


def vpad(s, w, align="l"):
    d = w - vlen(s)
    if d <= 0:
        return s
    return s + " " * d if align == "l" else " " * d + s


def render_table(headers, rows, aligns=None, plain=False, dim=None):
    """Render a bordered table that stays aligned even with ANSI colours."""
    aligns = aligns or ["l"] * len(headers)
    widths = [max(vlen(str(h)), *(vlen(str(r[i])) for r in rows)) if rows
              else vlen(str(h)) for i, h in enumerate(headers)]
    D = dim or (lambda s: s)

    if plain:
        out = ["  ".join(vpad(str(h), widths[i], aligns[i])
                         for i, h in enumerate(headers)).rstrip()]
        for r in rows:
            out.append("  ".join(vpad(str(c), widths[i], aligns[i])
                                 for i, c in enumerate(r)).rstrip())
        return "\n".join(out)

    def rule(left, mid, right):
        return D(left + mid.join("─" * (w + 2) for w in widths) + right)

    def line(cells):
        body = D("│") + D("│").join(
            " " + vpad(str(c), widths[i], aligns[i]) + " " for i, c in enumerate(cells))
        return body + D("│")

    return "\n".join([rule("╭", "┬", "╮"), line(headers),
                       rule("├", "┼", "┤")] + [line(r) for r in rows] +
                      [rule("╰", "┴", "╯")])


def color(on=True):
    if not on or not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return lambda s, c: s
    codes = {"b": "1", "dim": "2", "cy": "36", "gr": "32", "yl": "33", "rd": "31"}
    return lambda s, c: f"\033[{codes[c]}m{s}\033[0m"


# ── commands ─────────────────────────────────────────────────────────
def cmd_path(a):
    print(profile_dir(a.name))
    return 0


def cmd_status(a):
    C = color()
    D = lambda t: C(t, "dim")
    act = active_profile()

    headers = ["PROFILE", "ACCOUNT", "AUTH"]
    aligns  = ["l", "l", "l"]
    if a.dirs:
        headers.insert(1, "CONFIG DIR"); aligns.insert(1, "l")
    if not a.no_usage:
        headers += ["5-HOUR", "RESETS", "7-DAY", "RESETS", "AS OF"]
        aligns  += ["r", "l", "r", "l", "r"]

    def cells(bucket):
        """(percent, resets) cells for one limit."""
        if not bucket or bucket.get("pct") is None:
            return D("-"), D("-")
        if bucket.get("locked"):
            return C("locked", "rd"), D("-")
        pct = bucket["pct"]
        tone = "rd" if pct >= 90 else ("yl" if pct >= 75 else "gr")
        # the API returns floats, the cache ints - render both the same way
        shown = f"{pct:g}" if isinstance(pct, float) else str(pct)
        return C(f"{shown}%", tone), until(bucket["resets"])

    names = profile_names()
    live = {}
    if a.live and not a.no_usage:
        targets = [n for n in names if has_credentials(profile_dir(n))]
        if targets:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(fetch_live, profile_dir(n)): n for n in targets}
                for f in concurrent.futures.as_completed(futs):
                    live[futs[f]] = f.result()          # (usage, reason)

    rows = []
    for n in names:
        d = profile_dir(n)
        email = account_email(d) or D("(not logged in)")
        authed = has_credentials(d)
        name = C(f"* {n}", "b") if n == act else f"  {n}"

        row = [name, email, C("ok", "gr") if authed else D("none")]
        if a.dirs:
            row.insert(1, d.replace(HOME, "~"))
        if not a.no_usage:
            fresh, why = live.get(n, (None, ""))
            u = fresh or usage_of(d)
            if not u:
                row += [D("-"), D("-"), D("-"), D("-"), D("never used")]
            else:
                p5, r5 = cells(u.get("5h"))
                p7, r7 = cells(u.get("7d"))
                if u.get("live"):
                    when = C("live", "gr")
                elif a.live:
                    when = C(f"{ago(u['age'])} ({why or 'cached'})", "yl")
                else:
                    when = C(ago(u["age"]), "yl" if u["age"] > 86400 else "dim")
                row += [p5, r5, p7, r7, when]
        rows.append(row)

    print(render_table(headers, rows, aligns, plain=a.plain, dim=D))
    if not a.no_usage:
        if a.live:
            if any(v[0] for v in live.values()):
                print(D("live figures fetched from the Anthropic usage API"))
            stale = sorted(n for n, (v, _) in live.items() if v is None)
            if stale:
                reasons = {live[n][1] for n in stale}
                print(C(f"cached instead for: {', '.join(stale)}"
                        f"  ({', '.join(sorted(reasons))})", "yl"))
                if "token expired" in reasons:
                    print(D("a token refreshes when that profile runs claude - "
                            "open a session there, or use the cached figures"))
                if "rate limited" in reasons:
                    print(D("the usage endpoint is rate limited - try again shortly"))
        else:
            print(D("cached snapshot - refreshes at most every 5 min while a profile runs."
                    " use --live for current figures"))
    return 0


def cmd_sessions(a):
    C = color()
    D = lambda t: C(t, "dim")
    if a.profile:
        want = [a.profile]
    elif a.all_profiles:
        want = profile_names()
    else:
        want = [active_profile()]

    pattern = None
    if a.grep:
        try:
            pattern = re.compile(a.grep, re.I)
        except re.error as e:
            print(f"bad --grep pattern: {e}", file=sys.stderr)
            return 2

    target = os.path.abspath(a.dir)
    found = []
    for p in want:
        for f in transcripts(p):
            info = scan(f, pattern)
            if not info:
                continue
            cwd, branch, turns, mtime, summary = info
            if not a.all and cwd != target:
                continue
            found.append((mtime, p, os.path.basename(f)[:-6], cwd or "?", branch, turns, summary))
    found.sort(reverse=True)
    if not found:
        where = "any directory" if a.all else target
        what = f"matching '{a.grep}' " if a.grep else ""
        print(f"no sessions {what}in profile(s) {', '.join(want)} for {where}", file=sys.stderr)
        print("try:  claude-sessions -a       (all directories)", file=sys.stderr)
        print("      claude-sessions -A -a    (all profiles too)", file=sys.stderr)
        return 1
    if a.limit:
        found = found[:a.limit]

    multi = len(want) > 1
    headers = ["#", "WHEN", "TURNS", "SESSION ID", "SUMMARY"]
    aligns  = ["r", "l", "r", "l", "l"]
    if multi:
        headers.insert(1, "PROFILE"); aligns.insert(1, "l")
    if a.all:
        headers.insert(len(headers) - 1, "DIRECTORY"); aligns.insert(len(aligns) - 1, "l")

    def dircell(cwd, branch):
        path = cwd.replace(HOME, "~")
        if len(path) > 32:
            path = "…" + path[-31:]
        if branch and branch != "HEAD":
            b = branch if len(branch) <= 16 else branch[:15] + "…"
            return path + D(f" ({b})")
        return path

    # build every cell except SUMMARY, then give SUMMARY whatever is left
    width = shutil.get_terminal_size((120, 24)).columns
    n_fixed = len(headers) - 1

    def build(short_id):
        out = []
        for i, (mtime, p, sid, cwd, branch, turns, summary) in enumerate(found, 1):
            shown = sid[:8] if short_id else sid
            row = [str(i), age(mtime), str(turns), C(shown, "cy")]
            if multi:
                row.insert(1, p)
            if a.all:
                row.append(dircell(cwd, branch))
            out.append((row, summary))
        return out

    def overhead_of(part):
        w = [max(vlen(headers[i]), *(vlen(r[0][i]) for r in part))
             for i in range(n_fixed)]
        return sum(x + 3 for x in w) + 4            # borders and padding

    partial = build(False)
    if width - overhead_of(partial) < 30:           # too tight - shorten ids
        partial = build(True)
        headers[headers.index("SESSION ID")] = "ID"
    overhead = overhead_of(partial)
    room = max(20, min(width - overhead, 100))

    rows = []
    for row, summary in partial:
        text = summary if a.full or len(summary) <= room else summary[:room - 1] + "…"
        rows.append(row + [text])

    print(render_table(headers, rows, aligns, plain=a.plain, dim=D))
    return 0


def cmd_handoff(a):
    src_name = a.source or active_profile()
    src = profile_dir(src_name)
    dst = profile_dir(a.target)
    if not os.path.isdir(dst):
        print(f"no such profile: {a.target}", file=sys.stderr)
        print("available: " + ", ".join(profile_names()), file=sys.stderr)
        return 1
    if os.path.normpath(src) == os.path.normpath(dst):
        print(f"source and target are the same profile ({src_name})", file=sys.stderr)
        return 1

    hits = []
    if a.session:
        for f in transcripts(src_name):
            if os.path.basename(f).startswith(a.session):
                hits.append(f)
        if len(hits) > 1:
            print(f"ambiguous session prefix '{a.session}':", file=sys.stderr)
            for f in hits:
                print("  " + os.path.basename(f)[:-6], file=sys.stderr)
            return 1
    else:
        target = os.path.abspath(a.dir)
        for f in transcripts(src_name):
            info = scan(f)
            if info and info[0] == target:
                hits.append(f)
        hits.sort(key=os.path.getmtime, reverse=True)
        hits = hits[:1]

    if not hits:
        what = f"session '{a.session}'" if a.session else f"any session for {a.dir}"
        print(f"no match: {what} in profile {src_name}", file=sys.stderr)
        return 1

    f = hits[0]
    sid = os.path.basename(f)[:-6]
    enc = os.path.basename(os.path.dirname(f))
    outdir = os.path.join(dst, "projects", enc)
    os.makedirs(outdir, exist_ok=True)
    shutil.copy2(f, os.path.join(outdir, os.path.basename(f)))

    info = scan(f)
    C = color()
    print(f"handed off session {C(sid,'cy')}")
    print(f"  from: {src_name}   to: {a.target}")
    if info and info[0]:
        print(f"  dir : {info[0].replace(HOME,'~')}")
    print()
    print(f"  claude-profile {a.target} && claude --resume {sid}")
    return 0


def dir_size(path):
    total = 0
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n/1:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def cmd_remove(a):
    C = color()
    name = a.name
    if name == "default":
        print("refusing to remove 'default' - that is your original ~/.claude", file=sys.stderr)
        return 1
    pdir = profile_dir(name)
    if not os.path.isdir(pdir):
        print(f"no such profile: {name}", file=sys.stderr)
        print("available: " + ", ".join(profile_names()), file=sys.stderr)
        return 1

    email = account_email(pdir)
    n_sessions = sum(1 for _ in transcripts(name))
    size = human(dir_size(pdir))
    service = keychain_service(pdir) if IS_MAC else None

    print(f"about to permanently delete profile {C(name, 'yl')}")
    print(f"  directory : {pdir.replace(HOME, '~')}  ({size})")
    print(f"  account   : {email or '(not logged in)'}")
    print(f"  sessions  : {n_sessions} conversation(s) - deleted with it")
    if service and has_credentials(pdir):
        print(f"  keychain  : {service}")
    if name == active_profile():
        print(C("  note      : this is the profile active in your shell", "yl"))

    if not a.yes:
        try:
            if input("\ntype the profile name to confirm: ").strip() != name:
                print("aborted"); return 1
        except (EOFError, KeyboardInterrupt):
            print("\naborted"); return 1

    if service:
        try:
            subprocess.run(["security", "delete-generic-password",
                            "-a", os.environ.get("USER", ""), "-s", service],
                           capture_output=True, timeout=10)
        except Exception:
            pass
    shutil.rmtree(pdir, ignore_errors=True)

    if os.path.exists(pdir):
        print(f"could not fully remove {pdir}", file=sys.stderr)
        return 1
    print(f"removed profile {name}")
    if name == active_profile():
        print("  run 'claude-profile default' to leave the removed profile")
    return 0


def keychain_entries():
    """Every Claude Code credential service name currently in the Keychain."""
    if not IS_MAC:
        return []
    try:
        r = subprocess.run(["security", "dump-keychain"], capture_output=True,
                           text=True, timeout=20)
    except Exception:
        return []
    return sorted(set(re.findall(r'"(Claude Code-credentials[^"]*)"', r.stdout)))


def find_markers(root=None, max_depth=4, budget=3.0):
    """`.claude-profile` markers under $HOME, time-bounded."""
    root = root or HOME
    start, found = time.time(), []
    skip = {"node_modules", "Library", "Applications", ".git", ".Trash",
            "vendor", "venv", ".venv", "dist", "build", "Pictures", "Movies"}
    for dirpath, dirs, files in os.walk(root):
        if time.time() - start > budget:
            dirs[:] = []
            break
        depth = dirpath[len(root):].count(os.sep)
        if depth >= max_depth:
            dirs[:] = []
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith(".")]
        if ".claude-profile" in files:
            f = os.path.join(dirpath, ".claude-profile")
            try:
                with open(f) as fh:
                    name = fh.readline().strip()
            except OSError:
                name = ""
            found.append((f, name))
    return found


def rc_files():
    return [os.path.join(HOME, f) for f in (".zshrc", ".bashrc", ".bash_profile",
                                            ".profile", ".zprofile")]


# things worth copying into a new profile - never credentials or history
CLONEABLE = ["settings.json", "CLAUDE.md", "plugins", "skills", "agents", "commands"]
NEVER_CLONE = {".credentials.json", ".claude.json", "projects", "sessions", "history.jsonl"}


def cmd_clone(a):
    C = color()
    src, dst = profile_dir(a.source), profile_dir(a.target)
    if not os.path.isdir(src):
        print(f"no such profile: {a.source}", file=sys.stderr)
        return 1
    if a.target == "default":
        print("refusing to clone over 'default' - that is your original ~/.claude",
              file=sys.stderr)
        return 1
    if os.path.normpath(src) == os.path.normpath(dst):
        print("source and target are the same profile", file=sys.stderr)
        return 1
    os.makedirs(dst, exist_ok=True)

    copied, skipped = [], []
    for item in CLONEABLE:
        s_path, d_path = os.path.join(src, item), os.path.join(dst, item)
        if not os.path.exists(s_path):
            continue
        if os.path.exists(d_path) and not a.force:
            skipped.append(item)
            continue
        if os.path.isdir(s_path):
            shutil.rmtree(d_path, ignore_errors=True)
            shutil.copytree(s_path, d_path)
        else:
            shutil.copy2(s_path, d_path)
        copied.append(item)

    if copied:
        print(f"copied into {C(a.target, 'cy')}: " + ", ".join(copied))
    if skipped:
        print(C(f"already present, left alone: {', '.join(skipped)}", "dim"))
        print(C("pass --force to overwrite", "dim"))
    if not copied and not skipped:
        print(f"nothing to copy from {a.source}")
    print(C("credentials and conversation history are never cloned - "
            f"run 'claude-profile {a.target}' then /login", "dim"))
    return 0


def cmd_prune(a):
    """Delete transcripts older than N days. Dry run unless --yes."""
    C = color()
    D = lambda t: C(t, "dim")
    want = [a.profile] if a.profile else profile_names()
    cutoff = time.time() - a.older_than * 86400

    doomed, kept, freed = [], 0, 0
    for p in want:
        for f in transcripts(p):
            mtime = os.path.getmtime(f)
            if mtime < cutoff:
                doomed.append((mtime, p, f, os.path.getsize(f)))
                freed += os.path.getsize(f)
            else:
                kept += 1
    doomed.sort()

    if not doomed:
        print(f"nothing older than {a.older_than} days in {', '.join(want)}"
              f" ({kept} session(s) kept)")
        return 0

    headers = ["WHEN", "PROFILE", "SESSION ID", "DIRECTORY"]
    rows = []
    for mtime, p, f, _ in doomed[:a.limit or len(doomed)]:
        info = scan(f)
        cwd = (info[0] if info else "?") or "?"
        rows.append([age(mtime), p, C(os.path.basename(f)[:-6], "cy"),
                     cwd.replace(HOME, "~")])
    print(render_table(headers, rows, ["l", "l", "l", "l"], plain=a.plain, dim=D))
    if a.limit and len(doomed) > a.limit:
        print(D(f"...and {len(doomed) - a.limit} more (use -n 0 to list them all)"))

    print(f"\n{len(doomed)} session(s) older than {a.older_than} days, {human(freed)}"
          f"  ({kept} newer session(s) untouched)")
    if not a.yes:
        print(C("dry run - nothing deleted. pass --yes to delete.", "yl"))
        return 0

    gone = 0
    for _, _, f, _ in doomed:
        try:
            os.remove(f)
            gone += 1
        except OSError as e:
            print(f"could not delete {f}: {e}", file=sys.stderr)
    print(C(f"deleted {gone} session(s), freed {human(freed)}", "gr"))
    return 0


def cmd_best(a):
    """Name the signed-in profile with the most headroom."""
    C = color()
    best, table = None, []
    for n in profile_names():
        d = profile_dir(n)
        if not has_credentials(d):
            continue
        u = (None if a.cached else fetch_live(d)[0]) or usage_of(d)
        if not u:
            continue
        pcts = [b["pct"] for b in (u.get("5h"), u.get("7d"))
                if b and b.get("pct") is not None]
        if not pcts or any((u.get(k) or {}).get("locked") for k in ("5h", "7d")):
            continue
        worst = max(pcts)                       # a profile is only as free as its tightest limit
        table.append((worst, n, u))
        if best is None or worst < best[0]:
            best = (worst, n, u)

    if best is None:
        print("no signed-in profile has usable usage figures", file=sys.stderr)
        return 1
    if a.quiet:
        print(best[1])
        return 0
    def pct(v):
        if v is None:
            return "-"
        return f"{v:g}%" if isinstance(v, float) else f"{v}%"

    for worst, n, u in sorted(table):
        mark = "->" if n == best[1] else "  "
        tone = "gr" if worst < 75 else ("yl" if worst < 90 else "rd")
        five = (u.get("5h") or {}).get("pct")
        seven = (u.get("7d") or {}).get("pct")
        print(f"  {mark} {n:<12} {C(pct(worst) + ' used', tone)}"
              f"  (5h {pct(five)}, 7d {pct(seven)})")
    return 0


def _git(*args, cwd=None):
    try:
        r = subprocess.run(["git", *args], cwd=cwd or TOOLS_DIR,
                           capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def installed_version():
    """Version string, with the git description when the checkout has one."""
    code, out, _ = _git("describe", "--tags", "--always", "--dirty")
    return f"{__version__} ({out})" if code == 0 and out else __version__


def latest_release(timeout=6):
    """Newest published tag on GitHub, or None."""
    assert RELEASES_URL.startswith("https://")   # noqa: S101 - guards urlopen below
    req = urllib.request.Request(RELEASES_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "claude-profiles"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return (json.loads(r.read().decode()).get("tag_name") or "").lstrip("v") or None
    except Exception:
        return None


def _vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def cmd_update(a):
    C = color()
    D = lambda t: C(t, "dim")
    print(f"installed: {C(installed_version(), 'cy')}")

    latest = latest_release()
    if latest is None:
        print(D("could not reach GitHub to check for a newer release"))
    else:
        if _vtuple(latest) > _vtuple(__version__):
            print(f"available: {C(latest, 'gr')}  "
                  + D(f"https://github.com/{REPO}/releases/tag/v{latest}"))
        else:
            print(f"available: {latest}  " + D("(you are up to date)"))

    if a.check:
        return 0

    if not os.path.isdir(os.path.join(TOOLS_DIR, ".git")):
        print(f"\n{TOOLS_DIR.replace(HOME, '~')} is not a git checkout - "
              "update it the same way you installed it", file=sys.stderr)
        return 1

    code, dirty, _ = _git("status", "--porcelain")
    if code == 0 and dirty:
        print(C("\nlocal changes present - commit or stash them first:", "yl"))
        print(D("  " + "\n  ".join(dirty.splitlines()[:10])))
        return 1

    before = _git("rev-parse", "--short", "HEAD")[1]
    print(D("\ngit pull --ff-only"))
    code, out, err = _git("pull", "--ff-only")
    if code != 0:
        print(err or out, file=sys.stderr)
        return 1
    after = _git("rev-parse", "--short", "HEAD")[1]

    if before == after:
        print("already at the newest commit")
        return 0

    _, log, _ = _git("log", "--oneline", f"{before}..{after}")
    print(f"\n{before} -> {after}")
    for line in log.splitlines()[:15]:
        print("  " + line)

    _, changed, _ = _git("diff", "--name-only", before, after)
    if any(f.startswith("shell/") for f in changed.splitlines()):
        print(C(f"\nthe shell layer changed - {reload_hint()}", "yl"))
    else:
        print(D("\nonly the core changed - no shell restart needed"))
    return 0


SEG = " \033[2m│\033[0m "


def _dim(t):
    return f"\033[2m{t}\033[0m"


def _tone(pct, text):
    c = 31 if pct >= 90 else (33 if pct >= 75 else 32)
    return f"\033[{c}m{text}\033[0m"


def install_statusline(profile, show, force=False):
    """Write the statusLine setting into a profile's settings.json."""
    pdir = profile_dir(profile)
    if not os.path.isdir(pdir):
        return f"no such profile: {profile}"
    f = os.path.join(pdir, "settings.json")
    try:
        with open(f) as fh:
            cfg = json.load(fh)
    except FileNotFoundError:
        cfg = {}
    except ValueError:
        return f"{f} is not valid JSON - fix or move it first"
    existing = cfg.get("statusLine")
    if existing and not force:
        cur = (existing or {}).get("command", "")
        if "claude-profiles" not in cur:
            return f"{profile}: already has a different statusLine (pass --force)"
    cmd = (f'python3 "{os.path.join(TOOLS_DIR, "bin", "claude-profiles.py")}"'
           f" statusline --show {show}").replace(HOME, "$HOME")
    cfg["statusLine"] = {"type": "command", "command": cmd, "padding": 0}
    os.makedirs(pdir, exist_ok=True)
    if os.path.exists(f):
        shutil.copy2(f, f + ".bak")
    with open(f, "w") as fh:
        json.dump(cfg, fh, indent=2)
    return None


def cmd_statusline(a):
    """One line for Claude Code's statusLine setting.

    Claude Code pipes a JSON payload on stdin - rate limits, context usage,
    cost, model - and renders whatever we print. The active profile comes from
    CLAUDE_CONFIG_DIR, which the child process inherits.
    """
    if a.install or a.install_all:
        C = color()
        targets = profile_names() if a.install_all else [active_profile()]
        for p in targets:
            err = install_statusline(p, a.show, a.force)
            print(f"  {C('skip', 'yl')} {err}" if err
                  else f"  {C('ok  ', 'gr')} {p}: status line enabled")
        print("\nstart a new Claude Code session to see it")
        return 0

    try:
        blob = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except Exception:
        blob = {}
    if not isinstance(blob, dict):
        blob = {}

    def sub(key):
        v = blob.get(key)
        return v if isinstance(v, dict) else {}

    name = active_profile()
    pdir = profile_dir(name)
    want = set(a.show.split(",")) if a.show else set()
    on = lambda k: k in want          # noqa: E731

    parts = []
    if on("profile"):
        parts.append(_dim(name) if name == "default" else f"\033[1;35m{name}\033[0m")

    if on("account"):
        email = account_email(pdir)
        if email:
            parts.append(_dim(email))

    if on("model"):
        m = sub("model").get("display_name")
        if m:
            eff = sub("effort").get("level")
            parts.append(_dim(f"{m} {eff}" if eff and eff != "medium" else m))

    if on("dir"):
        cwd = sub("workspace").get("current_dir") or blob.get("cwd")
        if cwd:
            parts.append(_dim(os.path.basename(cwd.rstrip("/")) or cwd))

    if on("branch"):
        cwd = sub("workspace").get("current_dir") or blob.get("cwd") or os.getcwd()
        code, out, _ = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd)
        if code == 0 and out and out != "HEAD":
            parts.append(_dim(f"\u2387 {out}"))

    if on("context"):
        cw = sub("context_window")
        pct = cw.get("used_percentage")
        if isinstance(pct, (int, float)):
            size = cw.get("context_window_size")
            cell = _tone(pct, f"ctx {pct:g}%")
            if size:
                cell += _dim(f"/{int(size) // 1000}k")
            parts.append(cell)

    if on("limits"):
        rl = sub("rate_limits")
        bits = []
        for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
            b = rl.get(key)
            if isinstance(b, dict) and b.get("used_percentage") is not None:
                pct = b["used_percentage"]
                bits.append(_tone(pct, f"{label} {pct:g}%"))
        if not bits:                     # payload had none - fall back to the cache
            u = usage_of(pdir)
            for key, label in (("5h", "5h"), ("7d", "7d")):
                b = (u or {}).get(key)
                if b and b.get("pct") is not None:
                    bits.append(_tone(b["pct"], f"{label} {b['pct']:g}%"))
        parts += bits                    # each limit is its own segment

    if on("cost"):
        c = sub("cost").get("total_cost_usd")
        if isinstance(c, (int, float)) and c > 0:
            parts.append(_dim(f"${c:.2f}"))

    if on("lines"):
        c = sub("cost")
        add, rem = c.get("total_lines_added"), c.get("total_lines_removed")
        if add or rem:
            parts.append(f"\033[32m+{add or 0}\033[0m/\033[31m-{rem or 0}\033[0m")

    if on("version"):
        v = blob.get("version")
        if v:
            parts.append(_dim(f"cc {v}"))

    if on("session"):
        n = blob.get("session_name")
        if n:
            parts.append(_dim(n[:40]))

    print(SEG.join(parts))
    return 0


# Fields this tool relies on. Both come from Claude Code internals that are not
# a documented API, so they are worth checking against real data now and then.
TRANSCRIPT_FIELDS = ("type", "cwd", "message")
USAGE_BUCKETS = ("five_hour", "seven_day")


def check_transcript_format():
    """Parse a real transcript and confirm the fields we depend on are present.

    Returns (ok, detail). ok is None when there was nothing to check.
    """
    newest, newest_at = None, 0
    for name in profile_names():
        for f in transcripts(name):
            try:
                mtime = os.path.getmtime(f)
            except OSError:
                continue
            if mtime > newest_at:
                newest, newest_at = f, mtime
    if not newest:
        return None, "no transcripts on this machine yet"

    seen, users = set(), 0
    try:
        with open(newest, errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                seen.update(o.keys())
                if o.get("type") == "user" and _text((o.get("message") or {}).get("content")):
                    users += 1
    except OSError as e:
        return False, f"could not read {newest}: {e}"

    missing = [f for f in TRANSCRIPT_FIELDS if f not in seen]
    where = os.path.basename(newest)
    if missing:
        return False, f"{where} has no {', '.join(missing)} - claude-sessions will misread it"
    if users == 0:
        return False, f"{where} parsed, but no user messages were recognised"
    return True, f"{where}: {users} message(s) read, all expected fields present"


def check_usage_endpoint():
    """Call the usage endpoint for real and confirm its shape. (ok, detail)."""
    candidates = [n for n in profile_names() if has_credentials(profile_dir(n))]
    if not candidates:
        return None, "no signed-in profile to check with"
    for name in candidates:
        pdir = profile_dir(name)
        exp = token_expiry(pdir)
        if exp is not None and exp < time.time():
            continue                       # expired, would only tell us that
        usage, why = fetch_live(pdir)
        if usage:
            got = [k for k in ("5h", "7d") if usage.get(k)]
            return True, f"{name}: responded with {', '.join(got)}"
        if why in ("token expired", "rate limited", "unreachable"):
            return None, f"{name}: {why} - could not check"
        return False, f"{name}: {why} - the response no longer has the fields we read"
    return None, "every signed-in profile has an expired token"


def cmd_doctor(a):
    C = color()
    issues, warns = [], []

    def ok(msg):    print(f"  {C('ok  ', 'gr')} {msg}")
    def warn(msg):  print(f"  {C('warn', 'yl')} {msg}"); warns.append(msg)
    def bad(msg):   print(f"  {C('FAIL', 'rd')} {msg}"); issues.append(msg)

    print(C("environment", "b"))
    ok(f"claude-profiles {installed_version()}")
    for tool in ("python3", "claude"):
        path = shutil.which(tool)
        ok(f"{tool} found at {path}") if path else bad(f"{tool} is not on PATH")
    cd = os.environ.get("CLAUDE_CONFIG_DIR")
    if cd and not os.path.isdir(cd):
        bad(f"CLAUDE_CONFIG_DIR points at a missing directory: {cd}")
    elif cd:
        norm = os.path.realpath(cd)
        inside = norm.startswith(os.path.realpath(PROF_HOME) + os.sep)
        is_default = norm == os.path.realpath(DEFAULT_DIR)
        if inside or is_default:
            ok(f"CLAUDE_CONFIG_DIR -> {cd.replace(HOME, '~')}")
        else:
            warn(f"CLAUDE_CONFIG_DIR points outside {PROF_HOME.replace(HOME, '~')} "
                 f"({cd.replace(HOME, '~')}) - this tool will not see it as a profile")
    else:
        ok("CLAUDE_CONFIG_DIR unset (profile 'default')")
    dflt = os.environ.get("CLAUDE_DEFAULT_PROFILE")
    if dflt and dflt != "default" and not os.path.isdir(os.path.join(PROF_HOME, dflt)):
        bad(f"CLAUDE_DEFAULT_PROFILE='{dflt}' is not a profile")
    elif dflt:
        ok(f"CLAUDE_DEFAULT_PROFILE -> {dflt}")
    if not os.path.isdir(PROF_HOME):
        warn(f"{PROF_HOME.replace(HOME, '~')} does not exist yet")
    elif os.path.isdir(os.path.join(PROF_HOME, ".git")):
        bad(f"{PROF_HOME.replace(HOME, '~')} is a git repo - account data must never be committed")
    else:
        ok(f"account data at {PROF_HOME.replace(HOME, '~')} (not a git repo)")

    print(C("\nshell wiring", "b"))
    wired = []
    for rc in rc_files():
        if not os.path.isfile(rc):
            continue
        with open(rc, errors="replace") as fh:
            hits = [line for line in fh
                    if "claude-profiles." in line and line.strip().startswith("source")]
        if len(hits) > 1:
            bad(f"{os.path.basename(rc)} sources the shell layer {len(hits)} times - remove the duplicates")
        elif hits:
            target = hits[0].split('"')[1] if '"' in hits[0] else hits[0].strip()
            if os.path.isfile(os.path.expandvars(target.replace("$HOME", HOME))):
                ok(f"{os.path.basename(rc)} -> {os.path.basename(target)}")
            else:
                bad(f"{os.path.basename(rc)} sources a file that does not exist: {target}")
            wired.append(rc)
    if not wired:
        bad("no rc file sources the shell layer - run install.sh")

    print(C("\nprofiles", "b"))
    names = profile_names()
    for n in names:
        d = profile_dir(n)
        if has_credentials(d):
            ok(f"{n}: {account_email(d) or 'signed in'}")
        else:
            warn(f"{n}: not logged in - run 'claude-profile {n}' then /login")
        exp = token_expiry(d)
        if exp is not None and exp < time.time():
            warn(f"{n}: access token expired {ago(time.time() - exp)} - "
                 "--live will fall back to cached figures until you run claude there")
        cred = os.path.join(d, ".credentials.json")
        if os.path.isfile(cred):
            mode = os.stat(cred).st_mode & 0o777
            if mode & 0o077:
                bad(f"{n}: .credentials.json is {oct(mode)[2:]} - should be 600 "
                    f"(chmod 600 {cred.replace(HOME, '~')})")

    if IS_MAC:
        print(C("\nkeychain", "b"))
        live = {keychain_service(profile_dir(n)) for n in names}
        entries = keychain_entries()
        if not entries:
            warn("could not read the keychain (or no entries yet)")
        for e in entries:
            if e in live:
                ok(f"{e}")
            else:
                bad(f"{e} is orphaned - no profile maps to it "
                    f"(security delete-generic-password -a \"$USER\" -s \"{e}\")")

    print(C("\nproject markers", "b"))
    markers = find_markers()
    if not markers:
        ok("no .claude-profile markers found (nothing to verify)")
    for f, name in markers:
        where = f.replace(HOME, "~")
        if not name:
            bad(f"{where} is empty")
        elif name not in names:
            bad(f"{where} points at '{name}', which is not a profile")
        else:
            ok(f"{where} -> {name}")

    if a.check_upstream:
        print(C("\nclaude code integration", "b"))
        print(C("  checking against real data - this makes one network call", "dim"))
        for label, fn in (("transcript format", check_transcript_format),
                          ("usage endpoint", check_usage_endpoint)):
            res, detail = fn()
            if res is True:
                ok(f"{label}: {detail}")
            elif res is False:
                bad(f"{label}: {detail}")
            else:
                warn(f"{label}: {detail}")

    print()
    if issues:
        print(C(f"{len(issues)} problem(s), {len(warns)} warning(s)", "rd"))
        return 1
    if warns:
        print(C(f"no problems, {len(warns)} warning(s)", "yl"))
        return 0
    print(C("all checks passed", "gr"))
    return 0


def main():
    ap = argparse.ArgumentParser(prog="claude-profiles")
    ap.add_argument("--version", action="version",
                    version=f"claude-profiles {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("path", help="print a profile's config dir")
    p.add_argument("name"); p.set_defaults(fn=cmd_path)

    p = sub.add_parser("status", help="list profiles, accounts and usage")
    p.add_argument("--dirs", action="store_true", help="show each profile's config dir")
    p.add_argument("--no-usage", action="store_true", help="hide the usage columns")
    p.add_argument("--plain", action="store_true", help="no borders - easier to pipe into other tools")
    p.add_argument("--live", action="store_true",
                   help="fetch current usage from the API instead of the cache")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("sessions", help="list sessions readably")
    p.add_argument("-a", "--all", action="store_true")
    p.add_argument("-A", "--all-profiles", action="store_true")
    p.add_argument("-p", "--profile")
    p.add_argument("-n", "--limit", type=int, nargs="?", default=20, const=0)
    p.add_argument("-f", "--full", action="store_true")
    p.add_argument("-d", "--dir", default=os.getcwd())
    p.add_argument("--plain", action="store_true", help="no borders - easier to pipe")
    p.add_argument("-g", "--grep", metavar="PATTERN",
                   help="only sessions containing PATTERN (case-insensitive regex)")
    p.set_defaults(fn=cmd_sessions)

    p = sub.add_parser("update", help="check for and pull a newer version")
    p.add_argument("-c", "--check", action="store_true",
                   help="only report, do not pull")
    p.set_defaults(fn=cmd_update)

    p = sub.add_parser("prune", help="delete old conversation transcripts")
    p.add_argument("-o", "--older-than", type=int, default=90, metavar="DAYS",
                   help="age threshold in days (default 90)")
    p.add_argument("-p", "--profile", help="just this profile (default: all)")
    p.add_argument("-n", "--limit", type=int, default=20,
                   help="rows to list (0 for all)")
    p.add_argument("-y", "--yes", action="store_true", help="actually delete")
    p.add_argument("--plain", action="store_true")
    p.set_defaults(fn=cmd_prune)

    p = sub.add_parser("best", help="which account has the most headroom")
    p.add_argument("-q", "--quiet", action="store_true", help="print just the name")
    p.add_argument("--cached", action="store_true", help="skip the live fetch")
    p.set_defaults(fn=cmd_best)

    p = sub.add_parser("clone", help="copy settings from one profile into another")
    p.add_argument("source")
    p.add_argument("target")
    p.add_argument("-f", "--force", action="store_true", help="overwrite what is already there")
    p.set_defaults(fn=cmd_clone)

    p = sub.add_parser("statusline", help="one-line status for Claude Code's statusLine")
    p.add_argument("--show", default="profile,account,limits",
                   help="comma-separated segments, in order: profile, account, "
                        "model, dir, branch, context, limits, cost, lines, "
                        "version, session")
    p.add_argument("--install", action="store_true",
                   help="enable it for the active profile")
    p.add_argument("--install-all", action="store_true",
                   help="enable it for every profile")
    p.add_argument("--force", action="store_true",
                   help="replace an existing statusLine")
    p.set_defaults(fn=cmd_statusline)

    p = sub.add_parser("doctor", help="check the installation for problems")
    p.add_argument("-u", "--check-upstream", action="store_true",
                   help="also verify Claude Code's transcript format and usage "
                        "endpoint still match what this tool expects")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("remove", help="delete a profile and its credentials")
    p.add_argument("name")
    p.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    p.set_defaults(fn=cmd_remove)

    p = sub.add_parser("handoff", help="copy a session into another profile")
    p.add_argument("target")
    p.add_argument("session", nargs="?")
    p.add_argument("-s", "--source")
    p.add_argument("-d", "--dir", default=os.getcwd())
    p.set_defaults(fn=cmd_handoff)

    a = ap.parse_args()
    try:
        return a.fn(a)
    except BadProfileName as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
