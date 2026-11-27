# SPDX-License-Identifier: MPL-2.0
"""The verifier and the catalog builder, against files signed here with throwaway keys."""

import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import build_catalog  # noqa: E402
import nbt_files  # noqa: E402
import render_site  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def make_key(folder, name):
    private = Path(folder, f"{name}.key")
    subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072",
                    "-out", str(private)], check=True, capture_output=True)
    subprocess.run(["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(Path(folder, f"{name}-public.pem"))],
                   check=True, capture_output=True)
    return private


def sign(key, data):
    return subprocess.run(["openssl", "dgst", "-sha256", "-sign", str(key)], input=data,
                          capture_output=True, check=True).stdout


def package(key, app="doom", version="1.0.2", sequence=1000002, payload=b"\x7fELF" + b"\0" * 60, extra=""):
    manifest = (f"app={app}\npackage={'ab' * 16}\nversion={version}\nsequence={sequence}\n"
                f"platform=qnx6.5-armv7le\ncompat=nbt_6.5_armv7\nsize={len(payload)}\n"
                f"sha256={hashlib.sha256(payload).hexdigest()}\nbridge=1.7\nbridge-uses=show\n"
                f"bridge-optional=\n{extra}").encode()
    header = struct.pack(">8sIIQ", b"NBTMGR1\n", len(manifest), 384, len(payload))
    return header + manifest + sign(key, header + manifest) + payload


def release(key, version="0.3.1", sequence=3001):
    components = [(name, bytes([i]) * (i + 1)) for i, name in enumerate(nbt_files.COMPONENTS_V1)]
    components.append(("runner", b"runner"))
    manifest = f"version={version}\nsequence={sequence}\nplatform=qnx6.5-armv7le\ncompat=nbt-evo-dev\n"
    manifest += "".join(f"{n}_size={len(d)}\n{n}_sha256={hashlib.sha256(d).hexdigest()}\n" for n, d in components)
    header = struct.pack(">8sII", b"NBTRLS3\n", len(manifest), 384)
    return header + manifest.encode() + sign(key, header + manifest.encode()) + b"".join(d for _, d in components)


class Keys:
    folder = None

    @classmethod
    def get(cls):
        if cls.folder is None:
            cls.folder = tempfile.mkdtemp()
            cls.apps = make_key(cls.folder, "apps")
            cls.manager = make_key(cls.folder, "manager")
            cls.other = make_key(cls.folder, "other")
        return cls


class VerifierTest(unittest.TestCase):
    def setUp(self):
        self.keys = Keys.get()
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)

    def write(self, data):
        path = Path(self.work.name, "file")
        path.write_bytes(data)
        return path

    def test_package(self):
        info = nbt_files.read_package(self.write(package(self.keys.apps, extra="property=Licence|GPL\ntext=Hello\n")),
                                      Path(self.keys.folder, "apps-public.pem"))
        self.assertEqual((info["app"], info["version"], info["sequence"], info["bridge"]), ("doom", "1.0.2", "1000002", "1.7"))
        self.assertEqual(info["properties"], [{"label": "Licence", "value": "GPL"}])
        self.assertEqual(info["text"], ["Hello"])

    def test_package_refusals(self):
        public = Path(self.keys.folder, "apps-public.pem")
        good = package(self.keys.apps)
        for data, reason in ((package(self.keys.other), "bad signature"),
                             (good[:-1] + b"X", "payload digest"),
                             (good[:-1], "header"),
                             (package(self.keys.apps, app="manager"), "manifest")):
            with self.assertRaises(nbt_files.Invalid) as caught:
                nbt_files.read_package(self.write(data), public)
            self.assertEqual(str(caught.exception), reason)

    def test_release(self):
        public = Path(self.keys.folder, "manager-public.pem")
        info = nbt_files.read_release(self.write(release(self.keys.manager)), public)
        self.assertEqual((info["version"], info["sequence"], info["format"]), ("0.3.1", "3001", 3))
        with self.assertRaises(nbt_files.Invalid):
            nbt_files.read_release(self.write(release(self.keys.manager)[:-1] + b"X"), public)
        with self.assertRaises(nbt_files.Invalid):
            nbt_files.read_release(self.write(release(self.keys.apps)), public)


class FakeGitHub:
    """GitHub releases whose assets are files signed here; counts downloads."""

    def __init__(self, folder):
        self.folder, self.by_repo, self.downloads, self.next_id = folder, {}, [], 100

    def add(self, repo, tag, data, prerelease=False, name=None):
        self.next_id += 1
        path = Path(self.folder, f"asset{self.next_id}")
        path.write_bytes(data)
        asset = {"id": self.next_id, "name": name or f"x-{tag[1:]}.nbt", "state": "uploaded", "size": len(data),
                 "updated_at": "2026-11-01T00:00:00Z", "browser_download_url": f"https://example/{self.next_id}",
                 "path": path}
        self.by_repo.setdefault(repo, []).append({"tag_name": tag, "prerelease": prerelease, "draft": False,
                                                   "published_at": "2026-11-01T00:00:00Z",
                                                   "html_url": f"https://example/{tag}", "assets": [asset]})

    def releases(self, repo, token, app=None):
        found = [r for r in self.by_repo.get(repo, []) if build_catalog.tag_version(r["tag_name"], app)]
        return sorted(found, key=lambda r: build_catalog.tag_version(r["tag_name"], app), reverse=True)

    def download(self, asset, target):
        self.downloads.append(asset["id"])
        data = asset["path"].read_bytes()
        target.write_bytes(data)
        return hashlib.sha256(data).hexdigest()


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.keys = Keys.get()
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.folder = work.name
        self.github = FakeGitHub(self.folder)
        for name in ("releases", "download"):
            original = getattr(build_catalog, name)
            setattr(build_catalog, name, getattr(self.github, name))
            self.addCleanup(setattr, build_catalog, name, original)
        self.apps = Path(self.folder, "apps.json")
        self.allow([{"id": "doom", "repo": "NBTFoundry/nf-doom"}])

    def allow(self, entries, **extra):
        base = {"name": "Doom", "summary": "A game.", "license": "GPL", "category": "game"}
        self.apps.write_text(json.dumps({"apps": [{**base, **e, **extra} for e in entries]}))

    def build(self, previous=None):
        return build_catalog.build(self.apps, self.keys.folder, None, previous, log=lambda _: None)

    def versions(self, catalog):
        return [(r["version"], r["prerelease"]) for r in catalog["apps"][0]["releases"]]

    def test_tags_of_a_repository_with_several_applications(self):
        self.assertEqual(build_catalog.tag_version("clock-v1.2.3", "clock"), (1, 2, 3))
        self.assertEqual(build_catalog.tag_version("v1.2.3", "clock"), (1, 2, 3))
        self.assertIsNone(build_catalog.tag_version("clock2-v1.2.3", "clock"))
        self.assertIsNone(build_catalog.tag_version("clock-v1.2", "clock"))
        self.assertIsNone(build_catalog.tag_version("doom-v1.0.0", None))

    def test_stable_and_newer_beta(self):
        self.github.add("NBTFoundry/nf-doom", "v1.0.1", package(self.keys.apps, version="1.0.1", sequence=1000001))
        self.github.add("NBTFoundry/nf-doom", "v1.0.2", package(self.keys.apps))
        self.github.add("NBTFoundry/nf-doom", "v1.1.0", package(self.keys.apps, version="1.1.0", sequence=1001000), True)
        self.assertEqual(self.versions(self.build()), [("1.1.0", True), ("1.0.2", False)])

    def test_bad_newest_falls_back_and_withdrawn_skipped(self):
        self.github.add("NBTFoundry/nf-doom", "v1.0.1", package(self.keys.apps, version="1.0.1", sequence=1000001))
        self.github.add("NBTFoundry/nf-doom", "v1.0.2", package(self.keys.apps))
        self.github.add("NBTFoundry/nf-doom", "v1.0.3", package(self.keys.other, version="1.0.3", sequence=1000003))
        self.assertEqual(self.versions(self.build()), [("1.0.2", False)])
        self.allow([{"id": "doom", "repo": "NBTFoundry/nf-doom"}], withdrawn=["1.0.2"])
        self.assertEqual(self.versions(self.build()), [("1.0.1", False)])

    def test_other_app_id_refused(self):
        self.github.add("NBTFoundry/nf-doom", "v1.0.2", package(self.keys.apps, app="snes9x"))
        self.assertEqual(self.versions(self.build()), [])

    def test_previous_catalog_skips_downloads(self):
        self.github.add("NBTFoundry/nf-doom", "v1.0.2", package(self.keys.apps))
        first = self.build()
        self.assertEqual(len(self.github.downloads), 1)
        second = self.build(json.loads(json.dumps(first)))
        self.assertEqual(len(self.github.downloads), 1)
        self.assertEqual(second["apps"], first["apps"])

    def test_manager_release(self):
        self.allow([{"id": "manager", "repo": "NBTFoundry/manager"}])
        self.github.add("NBTFoundry/manager", "v0.3.1", release(self.keys.manager), True, name="nbt-manager-0.3.1.nbtr")
        files = self.build()["apps"][0]["releases"][0]["files"]
        self.assertEqual([(f["name"], f["version"]) for f in files], [("nbt-manager-0.3.1.nbtr", "0.3.1")])

    def test_allowlist_checks(self):
        for entry in ({"id": "Doom", "repo": "a/b"}, {"id": "doom", "repo": "a"},
                      {"id": "doom", "repo": "a/b", "icon": "../x.png"}, {"id": "doom", "repo": "a/b", "extra": 1},
                      {"id": "doom", "repo": "a/b", "cover": "icons/x.png"}, {"id": "doom", "repo": "a/b", "title": ""},
                      {"id": "doom", "repo": "a/b", "featured": "yes"}):
            self.allow([entry])
            with self.assertRaises(SystemExit):
                build_catalog.load_allowlist(self.apps)

    def test_landing_page_fields(self):
        self.allow([{"id": "doom", "repo": "NBTFoundry/nf-doom", "title": "Doom", "featured": True,
                     "icon": "icons/doom.svg", "cover": "screens/doom.webp"}])
        app = self.build()["apps"][0]
        self.assertEqual((app["title"], app["featured"], app["icon"], app["cover"]),
                         ("Doom", True, "icons/doom.svg", "screens/doom.webp"))
        self.allow([{"id": "doom", "repo": "NBTFoundry/nf-doom"}])
        app = self.build()["apps"][0]
        self.assertEqual((app["title"], app["featured"], app["cover"]), (None, False, None))

    def test_repository_allowlist(self):
        entries = build_catalog.load_allowlist(ROOT / "apps.json")
        self.assertGreater(len(entries), 1)
        for entry in entries:
            for field in ("icon", "cover"):
                if entry.get(field):
                    self.assertTrue((ROOT / "site" / entry[field]).is_file(), entry[field])


class SiteTest(unittest.TestCase):
    def test_render(self):
        catalog = {"schema": 1, "generated": "2026-11-23T09:00:00Z", "apps": [
            {"id": "x", "name": "<b>X</b>", "summary": "s", "repo": "NBTFoundry/nf-x", "license": "MPL-2.0",
             "category": "game", "icon": None, "releases": []}]}
        with tempfile.TemporaryDirectory() as out:
            render_site.render(catalog, ROOT / "site", Path(out, "site"))
            self.assertEqual(json.loads(Path(out, "site", "catalog.json").read_text()), catalog)
            self.assertTrue(Path(out, "site", "apps.js").is_file())
            page = Path(out, "site", "index.html").read_text()
            self.assertRegex(page, r'src="apps\.js\?v=[0-9a-f]{12}"')
            self.assertRegex(page, r'href="style\.css\?v=[0-9a-f]{12}"')
            self.assertFalse(list(Path(out, "site").rglob("*.license")))
            with self.assertRaises(SystemExit):
                render_site.render({"apps": None}, ROOT / "site", Path(out, "bad"))


if __name__ == "__main__":
    unittest.main()
