#!/usr/bin/env python3
"""
fetch_altitudes.py — Fill missing altitude values in track JSON files.

Scans all JSON files in the output directory for GPS points where alt_m is 0
or null, pools them across all files, and fetches elevations from Open-Topo-Data
in batches of up to 100.

Usage:
    py fetch_altitudes.py <output_dir>

Open-Topo-Data constraints:
    - Max 100 locations per request
    - 2 second wait between requests
    - Hard stop after 1000 requests
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL      = "https://api.opentopodata.org/v1/srtm30m"
BATCH_SIZE   = 100
WAIT_SECONDS = 2
MAX_CALLS    = 1000


def fetch_batch(lat_lon_list: list[tuple[float, float]]) -> list[float | None]:
    """Call Open-Topo-Data for up to 100 points. Returns elevations in metres."""
    locations = "|".join(f"{lat},{lon}" for lat, lon in lat_lon_list)
    url = f"{API_URL}?locations={locations}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read())
    return [r.get("elevation") for r in data.get("results", [])]


def needs_altitude(point: dict) -> bool:
    alt = point.get("alt_m")
    return alt is None or alt == 0


def main() -> None:
    out_dir = Path(r"C:\python-projects\tracktaxonomy\public\alltracks")

    if not out_dir.is_dir():
        print(f"ERROR: {out_dir} is not a directory")
        sys.exit(1)

    json_files = sorted(out_dir.glob("*.json"))
    if not json_files:
        print(f"No JSON files found in {out_dir}")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Pass 1: load all files and collect every missing point
    # Each entry: (json_path, point_index)
    # ------------------------------------------------------------------
    file_data   = {}   # path -> parsed dict (kept in memory for writing back)
    missing     = []   # list of (json_path, point_index)

    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"WARNING: could not read {jf.name}: {exc}")
            continue
        file_data[jf] = data
        for i, pt in enumerate(data.get("gps_points", [])):
            if needs_altitude(pt):
                missing.append((jf, i))

    total_missing  = len(missing)
    total_batches  = -(-total_missing // BATCH_SIZE)  # ceil division
    calls_possible = min(total_batches, MAX_CALLS)

    print(f"Scanned {len(file_data)} JSON file(s).")
    print(f"Missing altitude points : {total_missing}")
    print(f"API calls needed        : {total_batches}  ({calls_possible} will be processed)")
    print(f"API calls limit         : {MAX_CALLS}")
    if total_batches > MAX_CALLS:
        print(f"WARNING: {total_batches - MAX_CALLS} batch(es) won't fit today — run again tomorrow.")
    print()

    if total_missing == 0:
        print("All points already have altitude data. Nothing to do.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Pass 2: fire batches
    # ------------------------------------------------------------------
    calls_made    = 0
    points_filled = 0
    dirty_files   = set()

    for batch_num in range(calls_possible):
        batch_slice = missing[batch_num * BATCH_SIZE : (batch_num + 1) * BATCH_SIZE]
        coords      = [
            (file_data[jf]["gps_points"][idx]["lat"],
             file_data[jf]["gps_points"][idx]["lon"])
            for jf, idx in batch_slice
        ]

        calls_remaining_before = MAX_CALLS - calls_made
        files_in_batch = len({jf for jf, _ in batch_slice})
        print(f"Batch {batch_num + 1}/{calls_possible}  "
              f"[{calls_remaining_before} API calls remaining]  "
              f"({files_in_batch} file(s) in this batch)")

        try:
            elevations = fetch_batch(coords)
            calls_made += 1
            for (jf, idx), elev in zip(batch_slice, elevations):
                if elev is not None:
                    file_data[jf]["gps_points"][idx]["alt_m"] = round(float(elev), 1)
                    points_filled += 1
                    dirty_files.add(jf)
        except (urllib.error.URLError, json.JSONDecodeError, Exception) as exc:
            calls_made += 1
            print(f"  ERROR: {exc}")

        if batch_num < calls_possible - 1:
            time.sleep(WAIT_SECONDS)

    # ------------------------------------------------------------------
    # Pass 3: write back only modified files
    # ------------------------------------------------------------------
    print()
    for jf in sorted(dirty_files):
        file_data[jf]["altitude_source"] = "opentopodata.org SRTM 30m"
        jf.write_text(json.dumps(file_data[jf], indent=2, ensure_ascii=False), encoding="utf-8")
        n_still_missing = sum(1 for pt in file_data[jf]["gps_points"] if needs_altitude(pt))
        status = "complete" if n_still_missing == 0 else f"{n_still_missing} points still missing"
        print(f"  Saved: {jf.name}  ({status})")

    print(f"\nDone.  API calls used: {calls_made}/{MAX_CALLS}  |  Points filled: {points_filled}")


if __name__ == "__main__":
    main()
