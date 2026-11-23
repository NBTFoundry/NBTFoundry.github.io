<!-- SPDX-License-Identifier: MPL-2.0 -->
# nbtfoundry.github.io

The landing page and the application catalog the phone app reads:
<https://nbtfoundry.github.io/catalog.json>.

- `apps.json`: the reviewed list of applications.
- `tools/build_catalog.py`: each app's newest stable release and a newer pre-release (beta), every
  file verified against the manager's `release/*.pem` (`tools/nbt_files.py`).
- `tools/render_site.py`: `site/` plus the app cards.
- `.github/workflows/pages.yml`: on push, every 30 minutes and by hand. GitHub pauses the schedule
  after 60 days without a commit here: re-enable it under Actions.

## Adding an application

Add an entry to `apps.json`:

| Field | |
| --- | --- |
| `id` | The package's app id (`--app`); a release whose package has another id is left out |
| `repo` | `owner/name`; releases tagged `vX.Y.Z`, one `.nbt` each (the manager's `app-release.yml`) |
| `name`, `summary`, `license`, `category` | Shown as is (`category`: `game`, `emulator`, `tool`, `system`) |
| `icon` | Optional, `icons/<name>.png` in `site/` |
| `withdrawn` | Optional, versions never to list |

## Local

```sh
python3 -I -m unittest discover -s tests
GITHUB_TOKEN=$(gh auth token) python3 -I tools/build_catalog.py --keys ../manager/release --output out/catalog.json
python3 -I tools/render_site.py --catalog out/catalog.json --output _site
```

## Catalog

`schema` 1. `apps[]` in `apps.json` order: `id`, `name`, `summary`, `repo`, `license`, `category`,
`icon`, `releases[]` (newest first, at most a beta then a stable): `version`, `sequence` (a string),
`prerelease`, `date`, `page`, `compat`, `bridge`, `properties`, `text`, `files[]` (`name`, `url`,
`size`, `sha256`, `version`, `sequence`; the manager's also `format`). NBT Manager's releases carry two
files, the release and its step release.

## Licence

MPL-2.0 ([LICENSE](LICENSE)). The artwork is NBTFoundry's, under MPL-2.0.
