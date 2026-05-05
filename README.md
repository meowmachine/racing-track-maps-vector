# Racing Track Maps (Vector)

Vector track maps from two sources: **AIM RaceStudio 3** (real-world tracks) and **iRacing** (sim tracks). All maps are in SVG format.

**Key difference between sources:** iRacing SVGs include a dedicated turn-numbers layer (`turns.svg`). RaceStudio 3 tracks do not contain turn number data, so no turn markers are produced for those tracks.

---

# Tracks from RaceStudio 3

> Source directory: `from-racingstudio3/`

RaceStudio 3 is AIM Sport's data analysis software. It ships with a large library of real-world circuit maps stored as proprietary binary `.tkk` files. This directory contains a Python pipeline that converts those files into open, web-friendly formats (SVG, JSON, PNG).

## Directory structure

```
from-racingstudio3/
├── tkk_to_svg.py        # Core parser: .tkk → SVG
├── batch_convert.py     # Batch converter: produces SVG + JSON + PNG for every .tkk file
├── fetch_altitudes.py   # Fills missing altitude data via Open-Topo-Data API
├── build_manifest.py    # Builds a compact JSON index of all tracks for search/autocomplete
├── manifest.json        # Pre-built track manifest (output of build_manifest.py)
├── tkk-files/           # Source .tkk files from RaceStudio 3
└── output/              # Converted tracks (SVG, JSON, PNG per track)
```

## Python scripts

### tkk_to_svg.py

Core library. Parses the binary `.tkk` format and renders a smooth SVG track map.

- Reads the chunk-based binary structure used by RaceStudio 3 (12-byte chunk headers)
- Decodes GPS points stored as `int32 * 10⁻⁷` degrees with altitude in millimeters
- Projects lat/lon to a flat 2D canvas using an equirectangular projection
- Smooths the track outline using Catmull-Rom → cubic Bézier conversion
- Adds a perpendicular start/finish line marker
- Exposes a `points_to_svg()` function used by `batch_convert.py`

Not meant to be run directly — import it or call it via `batch_convert.py`.

---

### batch_convert.py

The main script you run to convert track files. For each `.tkk` file it produces three output files:

| Output | Contents |
|--------|----------|
| `{track name}.svg` | Vector track map |
| `{track name}.json` | Full metadata + GPS points array + logo filename |
| `{track name}_logo.png` | Venue logo extracted from the `.tkk` file (if present) |

Metadata extracted from the `.tkk` binary includes track name, venue ID, short name, country, track length (meters), reference GPS coordinates, start/finish GPS coordinates, surface type (asphalt / dirt / ice / gravel), timezone, and contact info (city, postal code, phone, URL).

**Usage:**

```powershell
python from-racingstudio3\batch_convert.py
```

Edit the `INPUT_DIR` and `OUTPUT_DIR` variables at the top of the script to point to your directories before running.

---

### fetch_altitudes.py

Many `.tkk` files have altitude recorded as zero. This script fills those gaps by calling the [Open-Topo-Data](https://www.opentopodata.org/) public API (SRTM 30 m model).

- Scans all `.json` files in the output directory
- Collects every GPS point where `alt_m` is `0` or `null`
- Batches them into requests of up to 100 points, with a 2-second wait between requests (per API limits)
- Writes the elevation values back into only the modified JSON files
- Adds an `altitude_source` field to indicate the data came from the API

**Usage:**

```powershell
python from-racingstudio3\fetch_altitudes.py
```

Run this after `batch_convert.py`. It modifies the JSON files in-place.

---

### build_manifest.py

Generates `manifest.json` — a compact, alphabetically sorted array of all tracks for use in browser-side search and autocomplete.

Each entry is a three-element array: `[name, city, country]`. The output is minified (no whitespace) for fast loading.

**Usage:**

```powershell
python from-racingstudio3\build_manifest.py
```

Run this last, after `batch_convert.py` (and optionally `fetch_altitudes.py`).

## Getting updated tracks from RaceStudio 3

RaceStudio 3 stores all its track map files here on Windows:

```
C:\AIM_SPORT\RaceStudio3\aim_tracks\
```

AIM regularly pushes new and updated tracks through the RaceStudio 3 update mechanism. To get the latest tracks:

1. Install [AIM RaceStudio 3](https://www.aim-sportline.com/en/software-race-studio3.htm)
2. Open RaceStudio 3 and let it download all available updates
3. Close RaceStudio 3
4. Point `batch_convert.py` at the `aim_tracks` directory and run it:

```powershell
# Edit INPUT_DIR in batch_convert.py to:
# C:\AIM_SPORT\RaceStudio3\aim_tracks\

python from-racingstudio3\batch_convert.py
```

## Full pipeline

```
RaceStudio 3 .tkk files  (C:\AIM_SPORT\RaceStudio3\aim_tracks\)
        │
        ▼
  batch_convert.py   →   SVG + JSON + PNG per track
        │
        ▼
  fetch_altitudes.py →   JSON updated with SRTM elevation data
        │
        ▼
  build_manifest.py  →   manifest.json (search index)
```

## Requirements

```powershell
pip install requests
```

No other third-party packages are required. The SVG and JSON outputs use only the Python standard library.

---

# Tracks from iRacing

> Source directory: `from-iracing/`

iRacing is a subscription-based sim racing platform with a large licensed track library. This directory contains SVG track maps and metadata scraped from the iRacing member portal. There are no Python scripts here — the data was extracted entirely from the iRacing website using browser console JavaScript.

Unlike RaceStudio 3 tracks, **iRacing SVGs include a `turns.svg` layer with turn number labels.**

## Directory structure

```
from-iracing/
├── iracing-tracks-metadata.json   # Full metadata for all 149 tracks / 424 configurations
├── plan-licensed.md               # Step-by-step scraping guide for owned tracks
├── plan-unowned.md                # Step-by-step scraping guide for shop/unowned tracks
├── Road/                          # Road course SVGs
├── Oval/                          # Oval track SVGs
├── Dirt Road/                     # Dirt road course SVGs
└── Dirt Oval/                     # Dirt oval track SVGs
```

Each track configuration gets its own subfolder containing six SVG layers:

```
Road/adelaide/580-adelaide/
├── background.svg     # Track outline / filled shape
├── active.svg         # Active racing line
├── inactive.svg       # Inactive or alternate lines
├── pitroad.svg        # Pit lane
├── start-finish.svg   # Start/finish line marker
└── turns.svg          # Turn number labels
```

## SVG layers

| File | Contents |
|------|----------|
| `background.svg` | Filled track shape — the base layer |
| `active.svg` | The active driving line |
| `inactive.svg` | Inactive/alternative driving lines |
| `pitroad.svg` | Pit road path |
| `start-finish.svg` | Start/finish line marker |
| `turns.svg` | Turn number labels — **not available in RaceStudio 3 tracks** |

These layers are designed to be composited on top of each other to build a full track map display.

## Metadata (iracing-tracks-metadata.json)

The metadata file covers all 149 track families and 424 configurations. For each track it includes:

- Track name, location, latitude/longitude, timezone
- Category (Road / Oval / Dirt Road / Dirt Oval)
- About text and tech specs (scraped from the iRacing member portal)
- Per-configuration: length (miles), corners per lap, grid stalls, pit stalls, nominal lap time, night lighting, rain enabled, AI enabled
- SVG folder URL on iRacing's CDN and local path for every configuration

**Stats as of the last scrape (May 2026):**

| Category | Tracks | Configurations |
|----------|--------|----------------|
| Road | 71 | 253 |
| Oval | 54 | 137 |
| Dirt Oval | 18 | 20 |
| Dirt Road | 6 | 14 |
| **Total** | **149** | **424** |

## Scraping updated tracks yourself

iRacing adds new tracks and configurations periodically. To pull the latest data you'll need an **active iRacing membership**.

There are two scraping targets:

- **Owned/licensed tracks** — tracks you've purchased or that are included with your membership
  - https://members-ng.iracing.com/web/racing/licensed-content/tracks?filter=all&match=any&sort=track_name&tags=purchased&view=table


- **Shop/unowned tracks** — tracks available in the store that you haven't bought yet
  - https://members-ng.iracing.com/web/shop/tracks?filter=all&match=any&sort=track_name&tags=unowned&view=table


Install the [Claude Code Chrome extension](https://chromewebstore.google.com/detail/claude-code/ppdakckdlclmfdcemlahhmeijjbdllci), open it while on the iRacing member portal, and paste the contents of [plan-licensed.md](from-iracing/plan-licensed.md) (and/or [plan-unowned.md](from-iracing/plan-unowned.md)) into the chat. Claude will read the plan and execute all the scraping steps in the browser automatically, downloading the SVGs and metadata to a local folder you choose.

## SVG URL pattern

The iRacing CDN URL for any individual layer:

```
https://members-assets.iracing.com/public/track-maps/{js_var}/{trackId}-{configDirName}/{layer}.svg
```

These URLs are publicly accessible and can be fetched without a session cookie.
