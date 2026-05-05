# iRacing Track SVG + Metadata Scraper — Plan & Reference

## Overview

This document describes how to scrape track SVG map files and rich metadata from the iRacing members shop page for **unowned tracks** (tracks not yet purchased). The process was developed and refined over multiple sessions.

There are two separate scraping tasks:
1. **Licensed (owned) tracks** — from the Racing > Licensed Content > Tracks page
2. **Shop (unowned) tracks** — from the Shop > Tracks page ← this document focuses here

---

## What Is Being Scraped

For each unowned track in the shop:
- **6 SVG layer files** per track configuration: `background.svg`, `active.svg`, `inactive.svg`, `pitroad.svg`, `start-finish.svg`, `turns.svg`
- **Track metadata** (from React component `listData` prop via React fiber)
- **Track description text** (from the modal "About" tab via React Query / `scorpio_bff` tRPC endpoint)

---

## Source Pages

| Page | URL | Notes |
|------|-----|-------|
| Shop — All Tracks | `https://members-ng.iracing.com/web/shop/tracks?filter=all&match=any&sort=track_name&tags=unowned&view=table` | 79 unowned tracks (as of May 2026) |
| Shop — Road only | `https://members-ng.iracing.com/web/shop/tracks?filter=road&match=any&sort=track_name&tags=unowned&view=table` | 30 road tracks only |
| Licensed (owned) | `https://members-ng.iracing.com/web/racing/licensed-content/tracks?filter=road&match=any&sort=track_name&tags=purchased&view=table` | Use different script (see licensed_tracks notes) |

---

## Save Locations

| Content | Path |
|---------|------|
| Shop (unowned) SVGs + JSON | `C:\\python-projects\\\iracing-convert\\download-purchase\\{Category}\\{js_var}\\{trackId}-{configName}\\{layer}.svg` |
| Shop JSON metadata | `C:\\python-projects\\\iracing-convert\\download-purchase\\tracks-metadata.json` |
| Licensed (owned) SVGs + JSON | `C:\\python-projects\\\iracing-convert\\html\\licensed_tracks\\svg\\{js_var}\\{trackId}-{configName}\\{layer}.svg` |

### Category Directory Names
| iRacing category value | Directory name |
|------------------------|---------------|
| `road` (is_dirt=false) | `Road` |
| `oval` (is_dirt=false) | `Oval` |
| `dirt_road` / (is_dirt=true, is_oval=false) | `Dirt Road` |
| `dirt_oval` / (is_dirt=true, is_oval=true) | `Dirt Oval` |

---

## Technical Architecture

### 1. Track Metadata — React Fiber (`listData`)

The track table is rendered by a React component. All track data is available in the component's `listData` prop, accessible via the React fiber tree.

**Extraction:**
```javascript
function getFiber(el) {
  const key = Object.keys(el).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
  return key ? el[key] : null;
}
function getPropFromFiber(fiber, propName, maxDepth = 30) {
  let node = fiber;
  let depth = 0;
  while (node && depth < maxDepth) {
    const props = node.memoizedProps;
    if (props && props[propName] !== undefined) return props[propName];
    node = node.return;
    depth++;
  }
  return null;
}
const table = document.querySelector('table.table.table-striped');
const firstRow = table.querySelector('tbody tr');
const fiber = getFiber(firstRow);
const listData = getPropFromFiber(fiber, 'listData', 30);
// listData is an array of track groups. Each group = array of config objects.
// listData[i][0] = first config (representative for the track group)
```

**Key fields per config object:**
| Field | Description | Example |
|-------|-------------|---------|
| `track_id` | Numeric ID for this config | `584` |
| `track_name` | Pretty track name | `"St. Petersburg Grand Prix"` |
| `config_name` | Pretty config name | `"Grand Prix"` |
| `track_name_and_config` | Full pretty name | `"St. Petersburg Grand Prix"` |
| `track_dirpath` | Directory path (backslashes) | `"stpete"` or `"california\\oval"` |
| `js_var` | Track folder key | `"tracks_stpete"` |
| `category` | Category string | `"road"`, `"oval"`, `"dirt_oval"`, `"dirt_road"` |
| `is_oval` | Boolean | `false` |
| `is_dirt` | Boolean | `false` |
| `track_type_text` | Human readable type | `"Road Course"` |
| `has_svg_map` | Boolean — only download if true | `true` |
| `location` | City/Country | `"St. Petersburg, Florida, USA"` |
| `latitude`, `longitude` | Coordinates | `27.765`, `-82.627` |
| `time_zone` | TZ string | `"America/New_York"` |
| `logo` | Logo path | `"/img/logos/tracks/584.svg"` |
| `small_image` | Small image path | `"..."` |
| `price_display` | Price string | `"$14.95"` |
| `package_id` | Package ID | `539` |
| `sku` | SKU | `"..."` |
| `track_config_length` | Length in miles/km | `1.808` |
| `corners_per_lap` | Corner count | `14` |
| `grid_stalls` | Grid size | `60` |
| `number_pitstalls` | Pit stalls | `30` |
| `nominal_lap_time` | Seconds | `88.5` |
| `night_lighting` | Boolean | `false` |
| `rain_enabled` | Boolean | `false` |
| `ai_enabled` | Boolean | `true` |

### 2. SVG File URLs — CDN Pattern

SVG files are publicly accessible (no auth required) at:

```
https://members-assets.iracing.com/public/track-maps/{js_var}/{trackId}-{configName}/{layer}.svg
```

Where:
- `{js_var}` = e.g. `tracks_stpete`
- `{trackId}` = e.g. `584`
- `{configName}` = `track_dirpath` with backslashes replaced by hyphens: `track_dirpath.replace(/\\\\/g, '-')`
- `{layer}` = one of: `background`, `active`, `inactive`, `pitroad`, `start-finish`, `turns`

**Example:**
`https://members-assets.iracing.com/public/track-maps/tracks_stpete/584-stpete/background.svg`

### 3. Track Description Text — React Query / scorpio_bff

The "About" tab description is loaded via a **tRPC-style endpoint** called `scorpio_bff` through React Query (TanStack Query v4). The data is **fetched automatically when a track modal is opened** (URL changes to `?trackId=X`).

**How to access it:**
The React Query client is stored in the fiber tree. Find it by walking the fiber from any element:

```javascript
// Find QueryClient in the fiber tree
function findQueryClient(el) {
  function getFiber(el) {
    const key = Object.keys(el).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
    return key ? el[key] : null;
  }
  let node = getFiber(el);
  while (node) {
    let state = node.memoizedState;
    let si = 0;
    while (state && si < 5) {
      const val = state.memoizedState;
      if (val && typeof val === 'object' && typeof val.getQueryData === 'function') {
        return val; // This is the QueryClient
      }
      state = state.next;
      si++;
    }
    node = node.return;
  }
  return null;
}

// Usage:
const qc = findQueryClient(document.querySelector('#modal-track-about p'));
window._qClient = qc; // store for later use
```

**Query key format:**
```javascript
["scorpio_bff", "getTrackAssets", {"args": '{"trackId":584}'}]
// Note: args is a JSON STRING, not an object
```

**Getting cached data:**
```javascript
const data = qc.getQueryData(["scorpio_bff", "getTrackAssets", {"args": `{"trackId":${trackId}}`}]);
// data.detail_copy = HTML description
// data.detail_techspecs_copy = HTML tech specs
// data.coordinates = "lat,lng"
// data.track_id = numeric
```

**Triggering data load (clicking track link):**
The description data is only fetched when a track modal is opened. To trigger it programmatically, click the track's `<a>` element in the table row. The URL changes to `?trackId=X` and the React component fetches the description automatically.

**Wait for cache:**
```javascript
async function waitForCache(qc, trackId, maxWait = 10000) {
  const key = ["scorpio_bff", "getTrackAssets", {"args": `{"trackId":${trackId}}`}];
  const start = Date.now();
  while (Date.now() - start < maxWait) {
    const data = qc.getQueryData(key);
    if (data && data.track_id) return data;
    await new Promise(r => setTimeout(r, 200));
  }
  return null;
}
```

### 4. Closing the Modal

After scraping each track's description, close the modal with:
```javascript
const closeBtn = document.querySelector('.modal.fade.in a[data-dismiss="modal"]');
if (closeBtn) closeBtn.click();
```

### 5. File System Access API (Saving Files)

Files are saved using the browser's **File System Access API** (`showDirectoryPicker`). This requires a genuine user click gesture to trigger the OS directory picker.

```javascript
// Must be triggered from a real click event handler
const rootHandle = await window.showDirectoryPicker({ mode: 'readwrite' });

// Create nested directories
async function getOrCreateDir(parentHandle, name) {
  return await parentHandle.getDirectoryHandle(name, { create: true });
}

// Save a file
const fileHandle = await dirHandle.getFileHandle('filename.svg', { create: true });
const writable = await fileHandle.createWritable();
await writable.write(blobOrText);
await writable.close();
```

---

## Complete Step-by-Step Run Instructions

### Prerequisites
- Must be logged into iRacing at `https://members-ng.iracing.com`
- Browser must be Chrome/Edge (File System Access API support required)
- Target save directory must exist: `C:\\python-projects\\\iracing-convert\\download-purchase`

### Step 1 — Navigate to the right page

Go to: `https://members-ng.iracing.com/web/shop/tracks?filter=all&match=any&sort=track_name&tags=unowned&view=table`

Make sure:
- Filter = **All Tracks** (not just Road)
- Tags = **unowned** (to get only unpurchased tracks)
- View = **List View** (table view, not grid)

### Step 2 — Extract track metadata from React

Open the browser console (F12) and run:

```javascript
(function extractTracks() {
  function getFiber(el) {
    const key = Object.keys(el).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
    return key ? el[key] : null;
  }
  function getPropFromFiber(fiber, propName, maxDepth) {
    let node = fiber, depth = 0;
    while (node && depth < maxDepth) {
      if (node.memoizedProps && node.memoizedProps[propName] !== undefined) return node.memoizedProps[propName];
      node = node.return; depth++;
    }
    return null;
  }
  const table = document.querySelector('table.table.table-striped');
  const fiber = getFiber(table.querySelector('tbody tr'));
  window._listData = getPropFromFiber(fiber, 'listData', 30);
  console.log('Extracted', window._listData.length, 'track groups');
})();
```

### Step 3 — Find the React QueryClient

Open any track modal (click a track name), then run in console:

```javascript
(function findQC() {
  function getFiber(el) {
    const key = Object.keys(el).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
    return key ? el[key] : null;
  }
  const p = document.querySelector('#modal-track-about p');
  if (!p) { console.error('Modal not open or About tab not showing'); return; }
  let node = getFiber(p);
  while (node) {
    let state = node.memoizedState;
    let si = 0;
    while (state && si < 5) {
      const val = state.memoizedState;
      if (val && typeof val === 'object' && typeof val.getQueryData === 'function') {
        window._qClient = val;
        console.log('QueryClient found!');
        return;
      }
      state = state.next; si++;
    }
    node = node.return;
  }
  console.error('QueryClient not found');
})();
```

Close the modal after this step.

### Step 4 — Scrape all track descriptions

Run this in the console. It clicks each track in sequence, waits for the description to load, then closes the modal.

```javascript
(async function scrapeDescriptions() {
  const rows = Array.from(document.querySelectorAll('table.table-striped tbody tr'));
  const listData = window._listData;
  const qc = window._qClient;
  window._trackDescriptions = {};

  async function waitForCache(trackId) {
    const key = ["scorpio_bff", "getTrackAssets", {"args": `{"trackId":${trackId}}`}];
    const start = Date.now();
    while (Date.now() - start < 10000) {
      const data = qc.getQueryData(key);
      if (data && data.track_id) return data;
      await new Promise(r => setTimeout(r, 200));
    }
    return null;
  }

  // Close any open modal
  const existingClose = document.querySelector('.modal.fade.in a[data-dismiss="modal"]');
  if (existingClose) { existingClose.click(); await new Promise(r => setTimeout(r, 600)); }

  for (let i = 0; i < rows.length; i++) {
    const link = rows[i]?.querySelector('a');
    if (!link) continue;
    const trackId = listData[i]?.[0]?.track_id;
    const trackName = listData[i]?.[0]?.track_name;

    // Check cache first
    const cached = qc.getQueryData(["scorpio_bff", "getTrackAssets", {"args": `{"trackId":${trackId}}`}]);
    if (cached?.track_id) {
      window._trackDescriptions[trackId] = { detail_copy: cached.detail_copy, detail_techspecs_copy: cached.detail_techspecs_copy, track_id: cached.track_id, coordinates: cached.coordinates };
      console.log(`[${i+1}/${rows.length}] CACHED: ${trackName}`);
      continue;
    }

    link.click();
    await new Promise(r => setTimeout(r, 400));
    const data = await waitForCache(trackId);

    if (data) {
      window._trackDescriptions[trackId] = { detail_copy: data.detail_copy, detail_techspecs_copy: data.detail_techspecs_copy, track_id: data.track_id, coordinates: data.coordinates };
      console.log(`[${i+1}/${rows.length}] OK: ${trackName}`);
    } else {
      // DOM fallback
      const allPs = Array.from(document.querySelectorAll('#modal-track-about p'));
      window._trackDescriptions[trackId] = allPs.length > 0
        ? { detail_copy: allPs.map(p => `<p>${p.innerText}</p>`).join(''), detail_techspecs_copy: '', track_id: trackId, coordinates: '' }
        : { error: 'failed', track_id: trackId };
      console.warn(`[${i+1}/${rows.length}] ${data ? 'DOM fallback' : 'FAILED'}: ${trackName}`);
    }

    const cb = document.querySelector('.modal.fade.in a[data-dismiss="modal"]');
    if (cb) cb.click();
    await new Promise(r => setTimeout(r, 500));
  }
  console.log('Scrape complete:', Object.keys(window._trackDescriptions).length, 'descriptions');
})();
```

### Step 5 — Build the full data structure

```javascript
(function buildData() {
  const LAYERS = ['background', 'active', 'inactive', 'pitroad', 'start-finish', 'turns'];
  const CDN_BASE = 'https://members-assets.iracing.com/public/track-maps';
  const listData = window._listData;

  function getCategoryDir(cfg) {
    if (cfg.category === 'road' && !cfg.is_dirt) return 'Road';
    if (cfg.category === 'oval' && !cfg.is_dirt) return 'Oval';
    if (cfg.is_dirt && cfg.is_oval) return 'Dirt Oval';
    if (cfg.is_dirt && !cfg.is_oval) return 'Dirt Road';
    return 'Road'; // fallback
  }

  function stripHtml(html) {
    return (html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  }

  const allTracks = [];

  for (const trackGroup of listData) {
    const firstConfig = trackGroup[0];
    const parentTrackId = firstConfig.track_id;
    const descData = window._trackDescriptions[parentTrackId] || {};
    const categoryDir = getCategoryDir(firstConfig);

    const trackEntry = {
      track_id: firstConfig.track_id,
      track_name: firstConfig.track_name,
      track_name_short: firstConfig.js_var,
      js_var: firstConfig.js_var,
      category: firstConfig.category,
      category_dir: categoryDir,
      is_oval: firstConfig.is_oval,
      is_dirt: firstConfig.is_dirt,
      track_type_text: firstConfig.track_type_text,
      location: firstConfig.location,
      latitude: firstConfig.latitude,
      longitude: firstConfig.longitude,
      time_zone: firstConfig.time_zone,
      coordinates: descData.coordinates || '',
      logo: firstConfig.logo,
      small_image: firstConfig.small_image,
      folder: firstConfig.folder,
      about_html: descData.detail_copy || '',
      about_text: stripHtml(descData.detail_copy),
      techspecs_html: descData.detail_techspecs_copy || '',
      techspecs_text: stripHtml(descData.detail_techspecs_copy),
      price_display: firstConfig.price_display,
      package_id: firstConfig.package_id,
      sku: firstConfig.sku,
      num_configurations: trackGroup.filter(c => c.has_svg_map).length,
      configurations: []
    };

    for (const cfg of trackGroup) {
      if (!cfg.has_svg_map) continue;
      const configDirName = cfg.track_dirpath.replace(/\\/g, '-');
      const svgFolder = `${CDN_BASE}/${cfg.js_var}/${cfg.track_id}-${configDirName}`;
      const svgUrls = {};
      for (const layer of LAYERS) svgUrls[layer] = `${svgFolder}/${layer}.svg`;

      trackEntry.configurations.push({
        track_id: cfg.track_id,
        config_name: cfg.config_name,
        config_name_short: configDirName,
        track_dirpath: cfg.track_dirpath,
        track_name_and_config: cfg.track_name_and_config,
        track_config_length: cfg.track_config_length,
        corners_per_lap: cfg.corners_per_lap,
        grid_stalls: cfg.grid_stalls,
        number_pitstalls: cfg.number_pitstalls,
        nominal_lap_time: cfg.nominal_lap_time,
        track_type: cfg.track_type,
        track_type_text: cfg.track_type_text,
        is_oval: cfg.is_oval,
        is_dirt: cfg.is_dirt,
        night_lighting: cfg.night_lighting,
        rain_enabled: cfg.rain_enabled,
        ai_enabled: cfg.ai_enabled,
        fully_lit: cfg.fully_lit,
        svg_folder_url: svgFolder,
        svg_local_path: `${categoryDir}/${cfg.js_var}/${cfg.track_id}-${configDirName}`,
        svg_urls: svgUrls
      });
    }
    allTracks.push(trackEntry);
  }

  window._allTracksData = allTracks;
  const totalConfigs = allTracks.reduce((s, t) => s + t.configurations.length, 0);
  console.log('Built:', allTracks.length, 'tracks,', totalConfigs, 'configs,', totalConfigs * 6, 'SVG files');
})();
```

### Step 6 — Create the download button

```javascript
(function createButton() {
  const existing = document.getElementById('svg-dl-btn-wrap');
  if (existing) existing.remove();

  const wrap = document.createElement('div');
  wrap.id = 'svg-dl-btn-wrap';
  wrap.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999;background:#1a1a2e;border:2px solid #4fc3f7;border-radius:10px;padding:15px;font-family:monospace;color:#eee;min-width:320px;box-shadow:0 4px 20px rgba(0,0,0,0.6)';
  
  const LAYERS = ['background', 'active', 'inactive', 'pitroad', 'start-finish', 'turns'];
  const tracks = window._allTracksData;
  const totalFiles = tracks.reduce((s, t) => s + t.configurations.length, 0) * 6;

  wrap.innerHTML = `
    <div style="font-weight:bold;color:#4fc3f7;margin-bottom:8px">iRacing SVG Downloader</div>
    <div style="font-size:11px;color:#aaa;margin-bottom:10px">${tracks.length} tracks | ${totalFiles} SVG files + JSON</div>
    <button id="svg-dl-btn" style="background:#2e7d32;color:#fff;border:none;border-radius:6px;padding:10px;width:100%;cursor:pointer;font-size:13px;font-weight:bold;margin-bottom:10px">📁 SELECT SAVE DIRECTORY</button>
    <div style="background:#333;border-radius:4px;height:10px;display:none;margin-bottom:8px" id="svg-dl-prog-wrap"><div id="svg-dl-prog" style="background:#4fc3f7;height:100%;width:0%;transition:width .15s"></div></div>
    <div id="svg-dl-status" style="font-size:11px;color:#ccc">Select save directory to begin</div>
  `;
  document.body.appendChild(wrap);

  async function getOrCreateDir(parent, name) { return parent.getDirectoryHandle(name, { create: true }); }

  document.getElementById('svg-dl-btn').addEventListener('click', async () => {
    const btn = document.getElementById('svg-dl-btn');
    const status = document.getElementById('svg-dl-status');
    const progWrap = document.getElementById('svg-dl-prog-wrap');
    const prog = document.getElementById('svg-dl-prog');

    try {
      btn.disabled = true;
      btn.textContent = '⏳ Waiting for directory...';
      const rootHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
      progWrap.style.display = 'block';
      btn.textContent = '⬇️ Downloading...';

      let saved = 0, errors = 0;
      const errorLog = [];

      const metadata = {
        generated_at: new Date().toISOString(),
        source_page: window.location.href,
        total_tracks: tracks.length,
        total_configurations: tracks.reduce((s,t) => s + t.configurations.length, 0),
        total_svg_files: totalFiles,
        svg_layers: LAYERS,
        tracks
      };

      for (let ti = 0; ti < tracks.length; ti++) {
        const track = tracks[ti];
        status.textContent = `${ti+1}/${tracks.length}: ${track.track_name} [${track.category_dir}]...`;

        const catDir = await getOrCreateDir(rootHandle, track.category_dir);
        const trackDir = await getOrCreateDir(catDir, track.js_var);

        for (const cfg of track.configurations) {
          const configDir = await getOrCreateDir(trackDir, `${cfg.track_id}-${cfg.config_name_short}`);
          for (const layer of LAYERS) {
            try {
              const resp = await fetch(cfg.svg_urls[layer]);
              if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
              const blob = await resp.blob();
              const fh = await configDir.getFileHandle(`${layer}.svg`, { create: true });
              const w = await fh.createWritable();
              await w.write(blob); await w.close();
              saved++;
              prog.style.width = Math.round(saved / totalFiles * 100) + '%';
              if (saved % 60 === 0) status.textContent = `${saved}/${totalFiles} files... Track ${ti+1}/${tracks.length}`;
            } catch(e) {
              errors++;
              errorLog.push({ track: track.track_name, config: cfg.config_name, layer, url: cfg.svg_urls[layer], error: e.message });
            }
          }
        }
      }

      metadata.download_summary = { completed_at: new Date().toISOString(), saved_files: saved, errors, error_log: errorLog };

      // Save JSON
      const jh = await rootHandle.getFileHandle('tracks-metadata.json', { create: true });
      const jw = await jh.createWritable();
      await jw.write(JSON.stringify(metadata, null, 2));
      await jw.close();

      status.textContent = `✅ DONE! ${saved}/${totalFiles} SVGs, ${errors} errors. JSON saved.`;
      btn.textContent = errors === 0 ? '✅ Complete!' : `⚠️ Done (${errors} errors)`;
      btn.style.background = errors === 0 ? '#1b5e20' : '#e65100';
    } catch(e) {
      btn.disabled = false;
      btn.textContent = '📁 SELECT SAVE DIRECTORY';
      status.textContent = '❌ Error: ' + e.message;
    }
  });
  console.log('Download button created. Click it to start.');
})();
```

### Step 7 — Click the button and select the directory

1. Click the green **"📁 SELECT SAVE DIRECTORY"** button
2. An OS file picker dialog will appear
3. Navigate to: `C:\python-projects\iracing-convert\download-purchase`
4. Click **"Select Folder"**
5. Wait for the progress bar to complete — do **NOT** click anything else on the page during downloads

---

## Known Issues & Gotchas

### 1. React Query Cache Expiry
The `scorpio_bff` query results expire (staleTime is null). If you leave the page idle for a while, cached descriptions may be cleared and tracks will need to be re-clicked.

### 2. Modal Close Button
The close button selector is: `.modal.fade.in a[data-dismiss="modal"]`  
If modals don't close, also try: `document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }))`

### 3. showDirectoryPicker Requires Real User Gesture
You **cannot** programmatically trigger the file picker. A real mouse click on the button is required.

### 4. trackDirpath Backslash Conversion
`track_dirpath` uses Windows-style backslashes (e.g. `"california\\oval"`).  
Convert to hyphens for the URL: `track_dirpath.replace(/\\/g, '-')`  
Result: `"california-oval"`

### 5. Description Scraper Timing
Some tracks take longer to load their description (especially first time). The scraper waits up to 10 seconds per track. If a track times out, retry it individually.

### 6. tracks_stpete vs tracks_stpetersburg
Track `js_var` values are determined by iRacing and may differ from what you'd expect. Always use the value from `listData`, never guess it.

### 7. Page Navigation During Downloads
**Do NOT navigate away from the page while SVG downloads are running.** This aborts the async loop and no files will be saved after the point of navigation.

### 8. File System Access API — Browser Support
Only Chrome and Edge support this API. Firefox does not.

---

## File Output Structure

```
download-purchase/
├── tracks-metadata.json              ← all 79 tracks with full metadata
├── Road/
│   ├── tracks_stpete/
│   │   └── 584-stpete/
│   │       ├── background.svg
│   │       ├── active.svg
│   │       ├── inactive.svg
│   │       ├── pitroad.svg
│   │       ├── start-finish.svg
│   │       └── turns.svg
│   └── ... (more road tracks)
├── Oval/
│   └── ... (oval tracks)
├── Dirt Road/
│   └── ... (dirt road tracks)
└── Dirt Oval/
    └── ... (dirt oval tracks)
```

---

## tracks-metadata.json Schema

```json
{
  "generated_at": "2026-05-05T...",
  "source_page": "https://...",
  "total_tracks": 79,
  "total_configurations": 177,
  "total_svg_files": 1062,
  "svg_layers": ["background","active","inactive","pitroad","start-finish","turns"],
  "categories": [...],
  "tracks": [
    {
      "track_id": 584,
      "track_name": "St. Petersburg Grand Prix",
      "track_name_short": "tracks_stpete",
      "js_var": "tracks_stpete",
      "category": "road",
      "category_dir": "Road",
      "is_oval": false,
      "is_dirt": false,
      "track_type_text": "Road Course",
      "location": "St. Petersburg, Florida, USA",
      "latitude": 27.765,
      "longitude": -82.627,
      "time_zone": "America/New_York",
      "coordinates": "27.7650000,-82.6269440",
      "logo": "...",
      "small_image": "...",
      "about_html": "<p>...</p>",
      "about_text": "Plain text version...",
      "techspecs_html": "<p>...</p>",
      "techspecs_text": "Plain text version...",
      "price_display": "$14.95",
      "package_id": 539,
      "sku": "...",
      "num_configurations": 1,
      "configurations": [
        {
          "track_id": 584,
          "config_name": "Grand Prix",
          "config_name_short": "stpete",
          "track_dirpath": "stpete",
          "track_name_and_config": "St. Petersburg Grand Prix",
          "track_config_length": 1.808,
          "corners_per_lap": 14,
          "grid_stalls": 60,
          "number_pitstalls": 30,
          "nominal_lap_time": 88.5,
          "track_type": 5,
          "track_type_text": "Road Course",
          "is_oval": false,
          "is_dirt": false,
          "night_lighting": false,
          "rain_enabled": false,
          "ai_enabled": true,
          "fully_lit": false,
          "svg_folder_url": "https://members-assets.iracing.com/public/track-maps/tracks_stpete/584-stpete",
          "svg_local_path": "Road/tracks_stpete/584-stpete",
          "svg_urls": {
            "background": "https://.../background.svg",
            "active": "https://.../active.svg",
            "inactive": "https://.../inactive.svg",
            "pitroad": "https://.../pitroad.svg",
            "start-finish": "https://.../start-finish.svg",
            "turns": "https://.../turns.svg"
          }
        }
      ]
    }
  ],
  "download_summary": {
    "completed_at": "...",
    "saved_files": 1062,
    "errors": 0,
    "error_log": []
  }
}
```

---

## Stats (as of May 2026)

| Category | Tracks | Configs | SVG Files |
|----------|--------|---------|-----------|
| Road | ~21 | ~50 | ~300 |
| Oval | ~36 | ~83 | ~498 |
| Dirt Road | ~7 | ~17 | ~102 |
| Dirt Oval | ~15 | ~27 | ~162 |
| **Total** | **79** | **177** | **1062** |

---

## Related: Licensed (Owned) Tracks

For already-purchased tracks, the page is different and there is no "About" modal tab requirement. See the `html/licensed_tracks/svg/` directory and its companion metadata.

- Source page: `https://members-ng.iracing.com/web/racing/licensed-content/tracks?filter=road&match=any&sort=track_name&tags=purchased&view=table`  
- All categories: change `filter=road` to `filter=all`
- 212 configs (road only), 1272 SVG files
- Save location: `C:\python-projects\iracing-convert\html\licensed_tracks\svg`
- Structure: `{js_var}/{trackId}-{configName}/{layer}.svg` (no category subdirectory)
- **No description scraping needed** — the same scorpio_bff approach applies if descriptions are needed in future
