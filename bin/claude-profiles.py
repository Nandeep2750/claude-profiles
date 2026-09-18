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
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, sys, textwrap, time

HOME = os.path.expanduser("~")
PROF_HOME = os.environ.get("CLAUDE_PROFILE_HOME", os.path.join(HOME, ".claude-profiles"))
DEFAULT_DIR = os.path.join(HOME, ".claude")
IS_MAC = sys.platform == "darwin"


def profile_dir(name):
    return DEFAULT_DIR if name == "default" else os.path.join(PROF_HOME, name)


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


def usage_of(pdir):
    """Cached usage utilisation for a profile, or None.

    Claude Code refreshes this only when that profile actually runs, so it is a
    snapshot, never live. Always show its age alongside.
    """
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


def until(iso):
    """'in 54m' / 'in 1h 14m' / 'in 4d 23h' for an ISO timestamp, or '-'."""
    if not iso:
        return "-"
    try:
        dt = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return "-"
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


def scan(path):
    cwd = branch = None
    turns, summary = 0, ""
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
                if o.get("type") == "user" and not o.get("isMeta"):
                    t = _text((o.get("message") or {}).get("content"))
                    t = re.sub(r"<[^>]+>.*?</[^>]+>", " ", t, flags=re.S)
                    t = " ".join(t.split())
                    if not t or t.startswith("Caveat:"):
                        continue
                    turns += 1
                    if not summary:
                        summary = t
    except OSError:
        return None
    if turns == 0 and not summary:
        return None
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

    def rule(l, m, r):
        return D(l + m.join("─" * (w + 2) for w in widths) + r)

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
        return C(f"{pct}%", tone), until(bucket["resets"])

    rows = []
    for n in profile_names():
        d = profile_dir(n)
        email = account_email(d) or D("(not logged in)")
        authed = has_credentials(d)
        name = C(f"* {n}", "b") if n == act else f"  {n}"

        row = [name, email, C("ok", "gr") if authed else D("none")]
        if a.dirs:
            row.insert(1, d.replace(HOME, "~"))
        if not a.no_usage:
            u = usage_of(d)
            if not u:
                row += [D("-"), D("-"), D("-"), D("-"), D("never used")]
            else:
                p5, r5 = cells(u.get("5h"))
                p7, r7 = cells(u.get("7d"))
                stale = u["age"] > 86400
                row += [p5, r5, p7, r7, C(ago(u["age"]), "yl" if stale else "dim")]
        rows.append(row)

    print(render_table(headers, rows, aligns, plain=a.plain, dim=D))
    if not a.no_usage:
        print(D("usage is a cached snapshot - it refreshes only when that profile runs claude"))
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

    target = os.path.abspath(a.dir)
    found = []
    for p in want:
        for f in transcripts(p):
            info = scan(f)
            if not info:
                continue
            cwd, branch, turns, mtime, summary = info
            if not a.all and cwd != target:
                continue
            found.append((mtime, p, os.path.basename(f)[:-6], cwd or "?", branch, turns, summary))
    found.sort(reverse=True)
    if not found:
        where = "any directory" if a.all else target
        print(f"no sessions in profile(s) {', '.join(want)} for {where}", file=sys.stderr)
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


def main():
    ap = argparse.ArgumentParser(prog="claude-profiles")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("path", help="print a profile's config dir")
    p.add_argument("name"); p.set_defaults(fn=cmd_path)

    p = sub.add_parser("status", help="list profiles, accounts and usage")
    p.add_argument("--dirs", action="store_true", help="show each profile's config dir")
    p.add_argument("--no-usage", action="store_true", help="hide the usage columns")
    p.add_argument("--plain", action="store_true", help="no borders - easier to pipe into other tools")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("sessions", help="list sessions readably")
    p.add_argument("-a", "--all", action="store_true")
    p.add_argument("-A", "--all-profiles", action="store_true")
    p.add_argument("-p", "--profile")
    p.add_argument("-n", "--limit", type=int, nargs="?", default=20, const=0)
    p.add_argument("-f", "--full", action="store_true")
    p.add_argument("-d", "--dir", default=os.getcwd())
    p.add_argument("--plain", action="store_true", help="no borders - easier to pipe")
    p.set_defaults(fn=cmd_sessions)

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
    return a.fn(a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
