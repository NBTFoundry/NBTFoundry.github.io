#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Writes the published site: site/ as is, plus catalog.json, the file both the phone app
and the landing page read (site/apps.js renders the application cards from it)."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

HOOKS = ('id="app-grid"', 'id="manager-release"', 'id="catalog-generated"', 'src="apps.js"')
# Pages lets browsers keep a file 10 minutes: a page names these with their hash, so a reload
# after a deploy never runs a new page with an old script or stylesheet.
VERSIONED = (("apps.js", 'src="{}"'), ("style.css", 'href="{}"'))


def render(catalog, site, output):
    page = (site / "index.html").read_text(encoding="utf-8")
    for hook in HOOKS:
        if hook not in page:
            raise SystemExit(f"index.html has no {hook}")
    if not isinstance(catalog.get("apps"), list):
        raise SystemExit("catalog has no apps")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(site, output, ignore=shutil.ignore_patterns("*.license"))
    for page in output.glob("*.html"):
        text = page.read_text(encoding="utf-8")
        for name, attribute in VERSIONED:
            digest = hashlib.sha256((output / name).read_bytes()).hexdigest()[:12]
            text = text.replace(attribute.format(name), attribute.format(f"{name}?v={digest}"))
        page.write_text(text, encoding="utf-8")
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
