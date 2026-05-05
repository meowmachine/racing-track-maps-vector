# iRacing Licensed Tracks SVG + Metadata Scraping Plan

## Overview

This plan documents how to scrape SVG track maps and rich metadata from the iRacing **Licensed Content / My Licensed Tracks** page. Use this whenever you need to re-run the licensed tracks download.

---

## Target Page

**URL:** `https://members-ng.iracing.com/web/racing/licensed-content/tracks?filter=all&match=any&sort=track_name&tags=purchased&view=table`

- Filter: **All Tracks** (not just Road — this gets Road, Oval, Dirt Road, Dirt Oval)
- Tags: **purchased** (licensed/owned tracks)
- View: **table** (list view, required for React fiber extraction)

**Target Save Directory:** `C:\python-projects\iracing-convert\download-licensed`

---

## Step 1 — Extract listData from React Fiber

```javascript
function getFiber(el) {
  const key = Object.keys(el).find(k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance'));
  return key ? el[key] : null;
}
function getPropFromFiber(fiber, propName, maxDepth) {
  maxDepth = maxDepth || 30;
  let node = fiber, depth = 0;
  while (node && depth < maxDepth) {
    if (node.memoizedProps && node.memoizedProps[propName] !== undefined) {
      return { data: node.memoizedProps[propName], depth };
    }
    node = node.return;
    depth++;
  }
  return null;
}

const table = document.querySelector('table.table.table-striped');
const firstRow = table.querySelector('tbody tr');
const fiber = getFiber(firstRow);
const result = getPropFromFiber(fiber, 'listData', 30);
window._listData = result.data;
console.log('Found listData with', result.data.length, 'items');
```

**Expected result:** `_listData` is an array of arrays. Each inner array = all config objects for one track family. Field names: `track_id`, `track_name`, `track_dirpath`, `js_var`, `category`, `is_dirt`, `is_oval`, etc.

---

## Step 2 — Open First Modal and Find QueryClient

For the licensed tracks page, open a modal by clicking a View Track button (single-config tracks have a direct button, multi-config tracks have a dropdown). Then navigate to the About tab.

```javascript
// Click View Track for a single-config track (e.g., Adelaide Street Circuit, row 0)
const rows = document.querySelectorAll('table.table.table-striped tbody tr');
const row0 = rows[0];
const viewBtn = Array.from(row0.querySelectorAll('a')).find(a => a.textContent.trim().startsWith('View Track'));
viewBtn.click();
// Wait 1.5s for modal...
const modal = document.querySelector('.modal.fade.in');
const aboutTab = modal.querySelector('a[href="#modal-track-about"]');
aboutTab.click();
// Wait 1.5s for data...

// Find QueryClient in fiber
function findQueryClient(fiber, maxDepth) {
  maxDepth = maxDepth || 100;
  let node = fiber, depth = 0;
  while (node && depth < maxDepth) {
    let ms = node.memoizedState;
    while (ms) {
      if (ms.queue && ms.queue.dispatch && typeof ms.memoizedState === 'object' && ms.memoizedState && ms.memoizedState.getQueryData) {
        return ms.memoizedState;
      }
      ms = ms.next;
    }
    node = node.return;
    depth++;
  }
  return null;
}

const aboutEl = document.querySelector('#modal-track-about');
window._qClient = findQueryClient(getFiber(aboutEl), 150);
console.log('QueryClient found:', !!window._qClient);
```

**Query key format:** `["scorpio_bff", "getTrackAssets", {"args": "{\"trackId\":X}"}]`
Note: The `args` field is a JSON **string** (not object).

---

## Step 3 — Run Description Scraper Loop

Open each track modal, click About tab, wait for cache, close modal.

```javascript
// For multi-config tracks: click View Track to open dropdown, then click first dropdown item
// For single-config tracks: click View Track directly

async function scrapeTrackDescription(rowIndex) {
  const rows = document.querySelectorAll('table.table.table-striped tbody tr');
  const row = rows[rowIndex];
  
  // Open dropdown or direct modal
  const btns = row.querySelectorAll('a');
  const viewBtn = Array.from(btns).find(b => b.textContent.trim().startsWith('View Track'));
  viewBtn.click();
  await new Promise(r => setTimeout(r, 400));
  
  const dropdownItems = row.querySelectorAll('.dropdown-item');
  if (dropdownItems.length > 0) dropdownItems[0].click();
  
  await new Promise(r => setTimeout(r, 1500));
  
  const modal = document.querySelector('.modal.fade.in');
  if (!modal) return false;
  
  const aboutTab = modal.querySelector('a[href="#modal-track-about"]');
  if (aboutTab) aboutTab.click();
  
  await new Promise(r => setTimeout(r, 800));
  
  // Close modal
  const closeBtn = modal.querySelector('a[data-dismiss="modal"], button[data-dismiss="modal"]');
  if (closeBtn) closeBtn.click();
  else document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', keyCode: 27, bubbles: true }));
  
  await new Promise(r => setTimeout(r, 500));
  return true;
}

// Run for all 70 rows
(async () => {
  for (let i = 0; i < 70; i++) {
    await scrapeTrackDescription(i);
    console.log(`Scraped row ${i + 1}/70`);
  }
  console.log('All descriptions scraped!');
})();
```

**On timing errors:** If 6+ descriptions fail, re-run those rows with 800ms waits instead of 400ms.

---

## Step 4 — Build Data Structure

```javascript
function getCategoryDir(cfg) {
  if (cfg.is_dirt && cfg.is_oval) return 'Dirt Oval';
  if (cfg.is_dirt && !cfg.is_oval) return 'Dirt Road';
  if (cfg.category === 'oval' && !cfg.is_dirt) return 'Oval';
  return 'Road';
}

function htmlToText(html) {
  if (!html) return '';
  const tmp = document.createElement('div');
  tmp.innerHTML = html;
  return tmp.textContent.trim();
}

const layers = ['background', 'active', 'inactive', 'pitroad', 'start-finish', 'turns'];

window._allTracksData = window._listData.map(group => {
  const repr = group[0];
  const categoryDir = getCategoryDir(repr);
  const firstId = repr.track_id;
  const descData = window._qClient.getQueryData(['scorpio_bff', 'getTrackAssets', {args: JSON.stringify({trackId: firstId})}]);
  const about_html = descData ? (descData.detail_copy || '') : '';
  const techspecs_html = descData ? (descData.detail_techspecs_copy || '') : '';
  
  return {
    track_id: repr.track_id,
    track_name: repr.track_name.trim(),
    track_name_short: repr.js_var,
    js_var: repr.js_var,
    category: repr.category,
    category_dir: categoryDir,
    is_oval: repr.is_oval,
    is_dirt: repr.is_dirt,
    track_type: repr.track_type,
    track_type_text: repr.track_type_text,
    location: repr.location,
    latitude: repr.latitude,
    longitude: repr.longitude,
    time_zone: repr.time_zone,
    coordinates: descData ? (descData.coordinates || null) : null,
    logo: repr.logo,
    small_image: repr.small_image,
    folder: repr.folder,
    price_display: repr.price_display,
    package_id: repr.package_id,
    sku: repr.sku,
    num_configurations: group.length,
    about_html: about_html,
    about_text: htmlToText(about_html),
    techspecs_html: techspecs_html,
    techspecs_text: htmlToText(techspecs_html),
    configs: group.map(cfg => {
      const configDirName = cfg.track_dirpath.replace(/\\/g, '-');
      const svgFolderUrl = `https://members-assets.iracing.com/public/track-maps/${cfg.js_var}/${cfg.track_id}-${configDirName}`;
      const svgLocalPath = `${categoryDir}/${cfg.js_var}/${cfg.track_id}-${configDirName}`;
      return {
        track_id: cfg.track_id,
        config_name: cfg.track_name_and_config || cfg.track_name,
        config_name_short: configDirName,
        track_dirpath: cfg.track_dirpath,
        track_name_and_config: cfg.track_name_and_config || cfg.track_name,
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
        svg_folder_url: svgFolderUrl,
        svg_local_path: svgLocalPath,
        svg_urls: Object.fromEntries(layers.map(l => [l, `${svgFolderUrl}/${l}.svg`]))
      };
    })
  };
});
console.log('Built data for', window._allTracksData.length, 'tracks');
```

---

## Step 5 — Create Download Button

```javascript
const btn = document.createElement('button');
btn.textContent = '⬇️ Download Licensed Track SVGs';
btn.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999;background:#e63946;color:#fff;padding:12px 18px;border:none;border-radius:8px;font-size:14px;font-weight:bold;cursor:pointer';
document.body.appendChild(btn);

const progress = document.createElement('div');
progress.style.cssText = 'position:fixed;top:55px;right:10px;z-index:99999;background:#222;color:#0f0;padding:8px 14px;border-radius:6px;font-size:12px;font-family:monospace;max-width:380px;max-height:200px;overflow:auto;display:none';
document.body.appendChild(progress);

function log(msg) { 
  console.log('[DL] ' + msg);
  progress.style.display = 'block';
  progress.innerHTML += msg + '<br>';
  progress.scrollTop = progress.scrollHeight;
}

btn.addEventListener('click', async () => {
  btn.disabled = true;
  const dirHandle = await window.showDirectoryPicker({ mode: 'readwrite' });
  log('Dir: ' + dirHandle.name);
  
  const layers = ['background', 'active', 'inactive', 'pitroad', 'start-finish', 'turns'];
  let totalSvgs = 0, errors = 0;
  
  async function getOrCreateDir(parent, name) {
    return await parent.getDirectoryHandle(name, { create: true });
  }
  
  for (const track of window._allTracksData) {
    const catDir = await getOrCreateDir(dirHandle, track.category_dir);
    const jsVarDir = await getOrCreateDir(catDir, track.js_var);
    
    for (const cfg of track.configs) {
      const cfgDir = await getOrCreateDir(jsVarDir, `${cfg.track_id}-${cfg.config_name_short}`);
      for (const layer of layers) {
        try {
          const resp = await fetch(cfg.svg_urls[layer]);
          if (!resp.ok) { errors++; continue; }
          const svgText = await resp.text();
          const fh = await cfgDir.getFileHandle(`${layer}.svg`, { create: true });
          const w = await fh.createWritable();
          await w.write(svgText);
          await w.close();
          totalSvgs++;
        } catch (e) { errors++; }
      }
    }
    log(`✅ ${track.track_name}`);
  }
  
  // Save JSON
  const jsonFh = await dirHandle.getFileHandle('tracks-metadata.json', { create: true });
  const jw = await jsonFh.createWritable();
  await jw.write(JSON.stringify(window._allTracksData, null, 2));
  await jw.close();
  
  log(`✅ DONE! ${totalSvgs}/${totalSvgs + errors} SVGs, ${errors} errors`);
  btn.textContent = `✅ Done! ${totalSvgs} SVGs`;
});
```

---

## Step 6 — Click Button and Navigate to Target Directory

When the OS file picker opens:
1. Navigate to `C:\python-projects\iracing-convert\download-licensed`
2. Click "Select Folder" / "Open"
3. Wait for downloads to complete — do NOT navigate away from the page during download

---

## Directory Structure

```
download-licensed/
├── Road/
│   └── tracks_{name}/{trackId}-{configDir}/{layer}.svg
├── Oval/
│   └── tracks_{name}/{trackId}-{configDir}/{layer}.svg
├── Dirt Road/
│   └── tracks_{name}/{trackId}-{configDir}/{layer}.svg
├── Dirt Oval/
│   └── tracks_{name}/{trackId}-{configDir}/{layer}.svg
└── tracks-metadata.json
```

### Category → Directory Mapping

| iRacing `category` | `is_dirt` | `is_oval` | Directory |
|---|---|---|---|
| `road` | false | false | `Road` |
| `oval` | false | true | `Oval` |
| Any | true | false | `Dirt Road` |
| Any | true | true | `Dirt Oval` |

---

## SVG URL Pattern

```
https://members-assets.iracing.com/public/track-maps/{js_var}/{trackId}-{configDirName}/{layer}.svg
```

- `configDirName` = `track_dirpath.replace(/\\/g, '-')` (backslashes → hyphens)
- 6 layers per config: `background`, `active`, `inactive`, `pitroad`, `start-finish`, `turns`
- SVGs are **publicly accessible** — no authentication needed

---

## JSON Metadata Schema (per track)

```json
{
  "track_id": 556,
  "track_name": "Charlotte Motor Speedway",
  "track_name_short": "tracks_charlotte",
  "js_var": "tracks_charlotte",
  "category": "oval",
  "category_dir": "Oval",
  "is_oval": true,
  "is_dirt": false,
  "track_type": 1,
  "track_type_text": "Oval",
  "location": "Concord, North Carolina, USA",
  "latitude": 35.35,
  "longitude": -80.68,
  "time_zone": "America/New_York",
  "coordinates": "...",
  "logo": "/img/logos/tracks/...",
  "small_image": "https://...",
  "price_display": "Included",
  "num_configurations": 9,
  "about_html": "<p>...</p>",
  "about_text": "...",
  "techspecs_html": "<p>...</p>",
  "techspecs_text": "...",
  "configs": [
    {
      "track_id": 556,
      "config_name": "Charlotte Motor Speedway - Oval",
      "config_name_short": "charlotte-2025-oval",
      "track_dirpath": "charlotte\\2025\\oval",
      "track_name_and_config": "Charlotte Motor Speedway - Oval",
      "track_config_length": 1.5,
      "corners_per_lap": 4,
      "grid_stalls": 60,
      "number_pitstalls": 60,
      "nominal_lap_time": 30.0,
      "is_oval": true,
      "is_dirt": false,
      "night_lighting": true,
      "rain_enabled": false,
      "ai_enabled": true,
      "svg_folder_url": "https://members-assets.iracing.com/...",
      "svg_local_path": "Oval/tracks_charlotte/556-charlotte-2025-oval",
      "svg_urls": {
        "background": "https://...",
        "active": "https://...",
        "inactive": "https://...",
        "pitroad": "https://...",
        "start-finish": "https://...",
        "turns": "https://..."
      }
    }
  ]
}
```

---

## Known Issues / Fixes

| Issue | Root Cause | Fix |
|---|---|---|
| Tracks missed in download (e.g., charlotte, daytona_2011, indianapolis, phoenix) | These tracks appear in `_allTracksData` but with `configs: []` if listData was processed when the page was on `filter=road` instead of `filter=all` | Always navigate to `filter=all` before extracting listData |
| 6+ description errors | About tab takes >400ms to populate React Query cache | Use 800ms wait for retry, or poll for `#modal-track-about p` element |
| Modal doesn't open on click | `viewBtn.click()` triggers dropdown first; must click dropdown item | Click the dropdown item (first `.dropdown-item`) after clicking View Track |
| `queryFn` closure issue | queryFn captures trackId from component closure | Must open actual modal per track; cannot call queryFn directly |
| Download saved to wrong dir | `showDirectoryPicker` defaults to last used directory | Double-check dir name in progress log |

---

## Stats (as of May 2026 scrape)

| Metric | Value |
|---|---|
| Total track families | 70 |
| Total configurations | 247 |
| Total SVG files | 1,482 |
| Categories | Road (58), Oval (8), Dirt Oval (3), Dirt Road (1) |

*Note: 4 tracks were initially missed (charlotte, daytona_2011, indianapolis, phoenix) because they are Oval category and were processed during a `filter=road` session. They were recovered by re-running for filter=all and targeted separately (29 configs, 174 SVGs). The tracks-metadata.json should reflect all 70 tracks; use missing-tracks-supplement.json for the 4 recovered tracks if needed.*

---

## Quick Reference — Console Commands

```javascript
// Check how many tracks are loaded
window._listData.length  // should be 70 for all-tracks

// Check if QueryClient is available
!!window._qClient

// Check description cache for a specific track (e.g., Charlotte trackId 556)
window._qClient.getQueryData(['scorpio_bff', 'getTrackAssets', {args: JSON.stringify({trackId: 556})}])

// Count total configs
window._listData.flat().length  // 247

// Count configs with SVG map
window._listData.flat().filter(c => c.has_svg_map).length
```
