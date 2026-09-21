#!/usr/bin/env python3
"""Check the built documentation site before it is deployed.

Run after `mkdocs build`:

    python3 tests/check_site.py site

Catches what a plain build does not: a page that exists but serves a redirect
stub instead of content, a redirect that points at itself or at nothing, and
internal links that lead nowhere. The Commands page shipped broken for two days
because the only check asked "does this file exist", which a redirect stub
answers yes to.
"""
import os
import re
import sys
import urllib.parse

STUB = "Redirecting..."
MIN_WORDS = 120          # a real page has prose; a stub has a sentence


def read(path):
    with open(path, errors="replace") as fh:
        return fh.read()


def words_in(html):
    body = re.sub(r"<(script|style).*?</\1>", " ", html, flags=re.S)
    return len(re.sub(r"<[^>]+>", " ", body).split())


def main(root="site"):
    if not os.path.isdir(root):
        print(f"no such directory: {root} - run mkdocs build first", file=sys.stderr)
        return 2

    pages = sorted(
        os.path.relpath(os.path.join(d, "index.html"), root)
        for d, _, fs in os.walk(root) if "index.html" in fs
    )
    problems = []

    # 1. every page either has real content, or is a redirect to somewhere real
    for rel in pages:
        html = read(os.path.join(root, rel))
        here = os.path.dirname(rel)
        url = "/" + (here + "/" if here else "")
        if STUB in html:
            m = re.search(r'url=([^"\']+)', html)
            target = m.group(1) if m else None
            if not target:
                problems.append(f"{url} is a redirect with no destination")
                continue
            dest = os.path.normpath(os.path.join(here, target))
            if dest in (".", here):
                problems.append(f"{url} redirects to itself")
                continue
            if not os.path.isfile(os.path.join(root, dest, "index.html")):
                problems.append(f"{url} redirects to {target}, which does not exist")
            continue
        n = words_in(html)
        if n < MIN_WORDS:
            problems.append(f"{url} has only {n} words - is it really a page?")
        if "md-tabs__link" not in html:
            problems.append(f"{url} is missing the site navigation")

    # 2. every internal link resolves
    links = 0
    for rel in pages:
        html = read(os.path.join(root, rel))
        here = os.path.dirname(rel)
        body = re.split(r"<footer", html)[0]
        for href in sorted(set(re.findall(r'href="([^"#][^"]*)"', body))):
            # skip anything with a URL scheme, and protocol-relative links
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", href) or href.startswith(("//", "?")):
                continue
            if os.path.splitext(href.split("#")[0])[1] not in ("", ".html"):
                continue
            path = urllib.parse.unquote(href.split("#")[0])
            if not path:
                continue
            dest = os.path.normpath(os.path.join(here, path))
            links += 1
            if os.path.isfile(os.path.join(root, dest)):
                continue
            if os.path.isfile(os.path.join(root, dest, "index.html")):
                continue
            problems.append(f"/{here or ''} links to {href}, which does not exist")

    # 3. same-page anchors resolve
    anchors = 0
    for rel in pages:
        html = read(os.path.join(root, rel))
        ids = set(re.findall(r'id="([^"]+)"', html))
        for a in sorted(set(re.findall(r'href="#([^"]+)"', html))):
            anchors += 1
            if a not in ids:
                problems.append(f"/{os.path.dirname(rel)} has a dead anchor #{a}")

    print(f"  {len(pages)} pages, {links} links, {anchors} anchors checked")
    if problems:
        for p in problems:
            print(f"  FAIL {p}")
        print(f"\n{len(problems)} problem(s)")
        return 1
    print("  every page serves content and every link resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "site"))
