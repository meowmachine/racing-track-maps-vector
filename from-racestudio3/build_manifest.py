#!/usr/bin/env python3
"""
build_manifest.py — Generate a compact track manifest for browser autocomplete.

Produces a minified JSON array of arrays: [name, city, country]
Sorted alphabetically by track name.

Usage:
    py build_manifest.py <output_dir> [manifest.json]
"""

import json
import sys
from pathlib import Path


OUT_DIR = Path(r"C:\python-projects\tracktaxonomy\public\alltracks")
MANIFEST_DIR = Path(r"C:\python-projects\tracktaxonomy\public")
MANIFEST_PATH = MANIFEST_DIR / "manifest.tracks.json"


def main() -> None:
    out_dir       = OUT_DIR
    manifest_path = MANIFEST_PATH

    json_files = sorted(out_dir.glob("*.json"))
    # Exclude the manifest itself if it already exists in the same dir
    json_files = [f for f in json_files if f.resolve() != manifest_path.resolve()]

    entries = []
    errors  = 0

    for jf in json_files:
        try:
            # print(f"found: {jf.name}")
            data    = json.loads(jf.read_text(encoding="utf-8"))
            name    = data.get("full_name", "").strip()
            # print(f"name: {name}")
            contact = data.get("contact", {})
            city    = contact.get("city", "").strip()
            country = data.get("country", "").strip()
            if name:
                entries.append([name, city, country])
        except Exception as exc:
            print(f"WARNING: skipping {jf.name}: {exc}")
            errors += 1

    entries.sort(key=lambda e: e[0].lower())

    # separators=(',', ':') removes all whitespace → smallest valid JSON
    manifest_path.write_text(
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    size_kb = manifest_path.stat().st_size / 1024
    print(f"Wrote {manifest_path}")
    print(f"  {len(entries)} tracks, {size_kb:.1f} KB ({errors} skipped)")


if __name__ == "__main__":
    main()
