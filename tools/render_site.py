#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Writes the published site: site/ with the application cards and the manager's
release rendered from catalog.json into index.html, and catalog.json itself."""

import argparse
import hashlib
import json
import shutil
import time
from html import escape
from pathlib import Path

CATEGORIES = {"system": "System", "game": "Game", "emulator": "Emulator", "tool": "Tool"}


def size_text(size):
    return f"{size / 1048576:.1f} MB" if size >= 1048576 else f"{max(1, round(size / 1024))} KB"


def date_text(stamp):
    try:
        return time.strftime("%b %d, %Y", time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")).replace(" 0", " ")
    except (TypeError, ValueError):
        return ""


def tile(app):
    hue = int(hashlib.sha256(app["id"].encode()).hexdigest()[:4], 16) % 360
    if app.get("icon"):
        inner = f'<img src="{escape(app["icon"])}" alt="" width="56" height="56">'
    else:
        words = app["name"].replace("-", " ").split()
        inner = escape("".join(w[0] for w in words[:2]).upper())
    return f'<div class="tile" style="--hue: {hue}" aria-hidden="true">{inner}</div>'


def download(release, label, primary):
    main = release["files"][0]
    kind = "button small primary" if primary else "button small"
    return f'<a class="{kind}" href="{escape(main["url"])}">{escape(label)} {escape(release["version"])}</a>'


def card(app):
    releases = app["releases"]
    stable = next((r for r in releases if not r["prerelease"]), None)
    beta = next((r for r in releases if r["prerelease"]), None)
    chips = [f'<span class="chip">{escape(CATEGORIES.get(app["category"], app["category"].title()))}</span>']
    if not releases:
        chips.append('<span class="chip soon">Coming soon</span>')
    elif not stable:
        chips.append('<span class="chip beta">Beta</span>')
    newest = releases[0] if releases else None
    meta = [f'<span>Licence <b>{escape(app["license"])}</b></span>']
    if newest:
        meta.insert(0, f'<span><b>{escape(newest["version"])}</b> · {size_text(newest["files"][0]["size"])}'
                       f' · {escape(date_text(newest.get("date")))}</span>')
    buttons = []
    if stable:
        buttons.append(download(stable, "Download", True))
    if beta:
        buttons.append(download(beta, "Beta", not stable))
    buttons.append(f'<a class="button small" href="https://github.com/{escape(app["repo"])}">Source</a>')
    return (f'<article class="card" id="app-{escape(app["id"])}"><div class="card-head">{tile(app)}<div>'
            f'<h3>{escape(app["name"])}</h3><div class="chips">{"".join(chips)}</div></div></div>'
            f'<p class="summary">{escape(app["summary"])}</p><div class="meta">{"".join(meta)}</div>'
            f'<div class="actions">{"".join(buttons)}</div></article>')


def manager_line(app):
    if not app or not app["releases"]:
        return ""
    release = app["releases"][0]
    beta = ' <span class="chip beta">Beta</span>' if release["prerelease"] else ""
    return (f'<div class="release"><span>NBT Manager <b>{escape(release["version"])}</b>{beta}</span>'
            f'<a href="{escape(release["page"])}">Release notes</a></div>')


def render(catalog, site, output):
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(site, output, ignore=shutil.ignore_patterns("*.license"))
    apps = [a for a in catalog["apps"] if a["id"] != "manager"]
    apps.sort(key=lambda a: not a["releases"])  # released first, then allowlist order
    manager = next((a for a in catalog["apps"] if a["id"] == "manager"), None)
    page = (output / "index.html").read_text(encoding="utf-8")
    for marker, html in (("<!-- apps -->", "".join(card(a) for a in apps)),
                         ("<!-- manager -->", manager_line(manager)),
                         ("<!-- generated -->", escape(date_text(catalog["generated"])))):
        if marker not in page:
            raise SystemExit(f"index.html has no {marker}")
        page = page.replace(marker, html)
    (output / "index.html").write_text(page, encoding="utf-8")
    (output / "catalog.json").write_text(json.dumps(catalog, separators=(",", ":")) + "\n", encoding="ascii")
    (output / ".nojekyll").write_text("")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--site", default="site", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    render(json.loads(args.catalog.read_text(encoding="utf-8")), args.site, args.output)


if __name__ == "__main__":
    main()
