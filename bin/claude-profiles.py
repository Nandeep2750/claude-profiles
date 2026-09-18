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
import argparse, hashlib, json, os, re, shutil, subprocess, sys, textwrap, time

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
    rows = []
    for n in profile_names():
        d = profile_dir(n)
        rows.append((n, d, account_email(d) or "(not logged in)",
                     "ok" if has_credentials(d) else "none"))
    act = active_profile()
    w = max(len(r[0]) for r in rows) + 2
    print(C(f"{'':<2}{'PROFILE':<{w}}{'CONFIG DIR':<34}{'ACCOUNT':<28}{'AUTH'}", "b"))
    for n, d, em, st in rows:
        mark = "*" if n == act else " "
        disp = d.replace(HOME, "~")
        line = f"{mark:<2}{n:<{w}}{disp:<34}{em:<28}"
        print(line + (C(st, "gr") if st == "ok" else C(st, "dim")))
    return 0


def cmd_sessions(a):
    C = color()
    if a.profile:
        want = [a.profile]
    elif a.all_profiles:
        want = profile_names()
    else:
        want = [active_profile()]

    target = os.path.abspath(a.dir)
    rows = []
    for p in want:
        for f in transcripts(p):
            info = scan(f)
            if not info:
                continue
            cwd, branch, turns, mtime, summary = info
            if not a.all and cwd != target:
                continue
            rows.append((mtime, p, os.path.basename(f)[:-6], cwd or "?", branch, turns, summary))
    rows.sort(reverse=True)
    if not rows:
        where = "any directory" if a.all else target
        print(f"no sessions in profile(s) {', '.join(want)} for {where}", file=sys.stderr)
        print("try:  claude-sessions -a       (all directories)", file=sys.stderr)
        print("      claude-sessions -A -a    (all profiles too)", file=sys.stderr)
        return 1
    if a.limit:
        rows = rows[:a.limit]

    multi = len(want) > 1
    width = shutil.get_terminal_size((120, 24)).columns
    head = f"{'':<3}{'WHEN':<9} {'TURNS':>5}  {'SESSION ID':<36}"
    if multi:
        head = f"{'':<3}{'PROFILE':<9}" + head[3:]
    print(C(head + "  SUMMARY", "b"))
    fixed = len(head) + 2
    for i, (mtime, p, sid, cwd, branch, turns, summary) in enumerate(rows, 1):
        lead = f"{i:>2} " + (f"{p:<9}" if multi else "")
        lead += f"{age(mtime):<9} {turns:>5}  {C(sid,'cy')}  "
        room = max(40, min(width - fixed - 3, 100))
        if a.full and len(summary) > room:
            wrapped = textwrap.wrap(summary, room) or [summary]
            print(lead + wrapped[0])
            for extra in wrapped[1:]:
                print(f"{'':<{fixed-2}}{extra}")
        else:
            print(lead + (summary if len(summary) <= room else summary[:room-1] + "…"))
        if a.all:
            tag = cwd.replace(HOME, "~") + (f"  ({branch})" if branch else "")
            print(C(f"{'':<{fixed-2}}{tag}", "dim"))
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

    p = sub.add_parser("status", help="list profiles and their accounts")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("sessions", help="list sessions readably")
    p.add_argument("-a", "--all", action="store_true")
    p.add_argument("-A", "--all-profiles", action="store_true")
    p.add_argument("-p", "--profile")
    p.add_argument("-n", "--limit", type=int, nargs="?", default=20, const=0)
    p.add_argument("-f", "--full", action="store_true")
    p.add_argument("-d", "--dir", default=os.getcwd())
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
