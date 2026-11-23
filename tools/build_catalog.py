#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Builds catalog.json: for each application in apps.json, its newest stable
release and a newer pre-release (beta), with the signed files the phone app
downloads. Every file is downloaded once and verified (tools/nbt_files.py); a
file the previous catalog already verified (same asset, same update time) is
taken from it."""

import argparse
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nbt_files  # noqa: E402

SCHEMA = 1
API = "https://api.github.com"
DOWNLOAD_MAX = 200 * 1024 * 1024
ATTEMPTS = 6
TAG = re.compile(r"v(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\.(0|[1-9][0-9]{0,2})\Z")
REPO = re.compile(r"[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}\Z")
ICON = re.compile(r"icons/[a-z0-9_-]{1,48}\.(png|svg|webp)\Z")
TEXT_LIMITS = {"name": 40, "summary": 160, "license": 80, "category": 20}


def fail(message):
    raise SystemExit(f"apps.json: {message}")


def load_allowlist(path):
    """The reviewed list of applications (README.md, "Adding an application")."""
    entries = json.loads(Path(path).read_text(encoding="utf-8")).get("apps")
    if not isinstance(entries, list) or not entries:
        fail("no apps")
    seen = set()
    for entry in entries:
        app = entry.get("id")
        if not isinstance(app, str) or not (app == "manager" or nbt_files.APP.fullmatch(app)) or app in seen:
            fail(f"bad or repeated id {app!r}")
        seen.add(app)
        if not isinstance(entry.get("repo"), str) or not REPO.fullmatch(entry["repo"]):
            fail(f"{app}: bad repo")
        for field, limit in TEXT_LIMITS.items():
            value = entry.get(field)
            if not isinstance(value, str) or not 0 < len(value) <= limit or value != value.strip():
                fail(f"{app}: {field} must be 1 to {limit} characters")
        if entry.get("icon") is not None and not (isinstance(entry["icon"], str) and ICON.fullmatch(entry["icon"])):
            fail(f"{app}: icon must be icons/<name>.png|svg|webp")
        withdrawn = entry.get("withdrawn", [])
        if not isinstance(withdrawn, list) or not all(isinstance(v, str) for v in withdrawn):
            fail(f"{app}: withdrawn must list versions")
        unknown = set(entry) - {"id", "repo", "icon", "withdrawn", *TEXT_LIMITS}
        if unknown:
            fail(f"{app}: unknown fields {sorted(unknown)}")
    return entries


def request(url, token, accept="application/vnd.github+json"):
    headers = {"Accept": accept, "User-Agent": "nbtfoundry-catalog", "X-GitHub-Api-Version": "2022-11-28"}
    req = urllib.request.Request(url, headers=headers)
    if token and url.startswith(API + "/"):
        # Never forwarded on a redirect (downloads redirect to another host).
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    return urllib.request.urlopen(req, timeout=60)


def releases(repo, token):
    """Published vX.Y.Z releases, newest version first."""
    with request(f"{API}/repos/{repo}/releases?per_page=50", token) as response:
        listed = json.load(response)
    found = []
    for release in listed:
        match = TAG.fullmatch(release.get("tag_name") or "")
        if match and not release.get("draft"):
            found.append(((int(match[1]), int(match[2]), int(match[3])), release))
    return [release for _, release in sorted(found, key=lambda item: item[0], reverse=True)]


def download(asset, target):
    """The public download (the phone's URL), checked against the announced size; its SHA-256."""
    size = asset["size"]
    if not 0 < size <= DOWNLOAD_MAX:
        raise nbt_files.Invalid("size")
    written, digest = 0, nbt_files.hashlib.sha256()
    with request(asset["browser_download_url"], None, "application/octet-stream") as response, \
            target.open("wb") as out:
        while True:
            block = response.read(1 << 20)
            if not block:
                break
            written += len(block)
            if written > size:
                raise nbt_files.Invalid("larger than announced")
            digest.update(block)
            out.write(block)
    if written != size:
        raise nbt_files.Invalid("truncated download")
    return digest.hexdigest()


def previous_files(catalog):
    """Asset id -> (asset update time, the release record that holds it)."""
    cached = {}
    if catalog and catalog.get("schema") == SCHEMA:
        for app in catalog.get("apps", []):
            for release in app.get("releases", []):
                for item in release.get("files", []):
                    cached[item.get("asset")] = (item.get("updated"), release)
    return cached


def verify_release(entry, release, keys, cached, work):
    """The catalog record of one GitHub release, or None when it has no file for the catalog."""
    manager = entry["id"] == "manager"
    suffix = ".nbtr" if manager else ".nbt"
    assets = [a for a in release.get("assets", []) if a.get("name", "").endswith(suffix) and a.get("state") == "uploaded"]
    if not assets or (not manager and len(assets) != 1):
        return None
    hit = [cached.get(a["id"]) for a in assets]
    if (all(h and h[0] == a["updated_at"] for h, a in zip(hit, assets)) and len({id(h[1]) for h in hit}) == 1
            and len(hit[0][1].get("files", [])) == len(assets)):
        record = dict(hit[0][1])
    else:
        files = []
        for asset in assets:
            target = Path(work, f"{asset['id']}{suffix}")
            digest = download(asset, target)
            info = (nbt_files.read_release(target, keys / "manager-public.pem") if manager
                    else nbt_files.read_package(target, keys / "apps-public.pem"))
            if info["app"] != entry["id"]:
                raise nbt_files.Invalid(f"package is {info['app']}, not {entry['id']}")
            target.unlink()
            item = {"name": asset["name"], "url": asset["browser_download_url"], "size": asset["size"],
                    "sha256": digest, "asset": asset["id"], "updated": asset["updated_at"],
                    "version": info["version"], "sequence": info["sequence"]}
            if manager:
                item["format"] = info["format"]
            files.append((info, item))
        files.sort(key=lambda pair: int(pair[0]["sequence"]), reverse=True)
        main = files[0][0]
        record = {"version": main["version"], "sequence": main["sequence"], "compat": main["compat"],
                  "bridge": main.get("bridge"), "properties": main.get("properties", []),
                  "text": main.get("text", []), "files": [item for _, item in files]}
    record.update(prerelease=bool(release.get("prerelease")), date=release.get("published_at"),
                  page=release.get("html_url"))
    return record


def catalog_entry(entry, keys, token, cached, work, log):
    """The application's newest verified stable release and a newer pre-release, newest first."""
    stable = beta = None
    attempts = 0
    for release in releases(entry["repo"], token):
        if release["tag_name"][1:] in entry.get("withdrawn", []) or (release.get("prerelease") and beta):
            continue
        if attempts == ATTEMPTS:
            break
        attempts += 1
        try:
            record = verify_release(entry, release, keys, cached, work)
        except (nbt_files.Invalid, OSError) as error:
            log(f"::warning::{entry['repo']} {release['tag_name']}: left out ({error})")
            continue
        if record is None:
            continue
        if record["prerelease"]:
            beta = record
        else:
            stable = record
            break
    if beta and stable and int(beta["sequence"]) <= int(stable["sequence"]):
        beta = None
    chosen = [r for r in (beta, stable) if r]
    out = {k: entry[k] for k in ("id", "name", "summary", "repo", "license", "category")}
    out["icon"] = entry.get("icon")
    out["releases"] = chosen
    return out


def build(apps_path, keys, token, previous=None, log=print):
    cached = previous_files(previous)
    apps = []
    with tempfile.TemporaryDirectory() as work:
        for entry in load_allowlist(apps_path):
            apps.append(catalog_entry(entry, Path(keys), token, cached, work, log))
            log(f"{entry['id']}: " + (", ".join(r["version"] for r in apps[-1]["releases"]) or "no release"))
    return {"schema": SCHEMA, "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "apps": apps}


def load_previous(source, token):
    if not source:
        return None
    try:
        if re.match(r"https://", source):
            with request(source, token, "application/json") as response:
                return json.load(response)
        return json.loads(Path(source).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"previous catalog not read ({error}); verifying every file")
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apps", default="apps.json", type=Path)
    parser.add_argument("--keys", required=True, type=Path, help="folder with apps-public.pem and manager-public.pem")
    parser.add_argument("--previous", help="the published catalog (URL or file), to skip files it verified")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    catalog = build(args.apps, args.keys, token, load_previous(args.previous, token))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=1, ensure_ascii=True) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
