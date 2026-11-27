<!-- SPDX-License-Identifier: MPL-2.0 -->
# nbtfoundry.github.io

The landing page and the application catalog the phone app reads:
<https://nbtfoundry.github.io/catalog.json>.

- `apps.json`: the reviewed list of applications.
- `tools/build_catalog.py`: each app's newest stable release and a newer pre-release (beta), every
  file verified against the manager's `release/*.pem` (`tools/nbt_files.py`).
- `site/`: the landing page. `site/apps.js` reads `catalog.json` in the browser and renders the
  application cards (the featured ones first, the others A to Z), NBT Manager's release and the
  update date: the same file as the phone app.
- `tools/share-card.html`: the link preview, `site/assets/share.png` (the command is in the file).
- `tools/render_site.py`: `site/` plus `catalog.json`.
- `.github/workflows/pages.yml`: on push, every 30 minutes and by hand. GitHub pauses the schedule
  after 60 days without a commit here: re-enable it under Actions.

## Adding an application

Add an entry to `apps.json`:

| Field | |
| --- | --- |
| `id` | The package's app id (`--app`); a release whose package has another id is left out |
| `repo` | `owner/name`; releases tagged `vX.Y.Z`, one `.nbt` each (the manager's `app-release.yml`), or `<id>-vX.Y.Z` in `NBTFoundry/community-apps` |
| `name`, `summary`, `license`, `category` | Shown as is (`category`: `game`, `emulator`, `tool`, `system`) |
| `title` | Optional, what the app gives ("PlayStation games"): the card's title, `name` under it |
| `icon` | Optional, `icons/<name>.svg` (or `.png`, `.webp`) in `site/` |
| `cover` | Optional, `screens/<name>.webp` (or `.png`) in `site/`, 8:3: a featured card's capture |
| `featured` | Optional, `true`: a large card before the others, in `apps.json` order |
| `withdrawn` | Optional, versions never to list |

## Local

```sh
python3 -I -m unittest discover -s tests
GITHUB_TOKEN=$(gh auth token) python3 -I tools/build_catalog.py --keys ../manager/release --output out/catalog.json
python3 -I tools/render_site.py --catalog out/catalog.json --output _site
```

## Catalog

`schema` 1. `apps[]` in `apps.json` order: `id`, `name`, `summary`, `repo`, `license`, `category`,
`icon`, `title`, `cover`, `featured` (the last three for the landing page; the phone app ignores them),
`releases[]` (newest first, at most a beta then a stable): `version`, `sequence` (a string),
`prerelease`, `date`, `page`, `compat`, `bridge`, `properties`, `text`, `notes`, `files[]` (`name`,
`url`, `size`, `sha256`, `version`, `sequence`), one per release. `notes` is what the release's page
says before its rule, as plain lines (`### Heading`, `- item` or a sentence; at most 24 of 300
characters, empty for a page without notes): the phone app shows them as what is new.

## Licence

MPL-2.0 ([LICENSE](LICENSE)). The artwork is NBTFoundry's, under MPL-2.0.
