#!/usr/bin/env python3
"""
batch_convert.py — Convert all .tkk files in a directory to SVG + JSON + logo PNG.

Usage:
    py batch_convert.py <tkk_dir> [output_dir]

For each .tkk file, three output files are written (named after the full track name):
    {track name}.svg        — smooth vector track map
    {track name}.json       — GPS coords + all track metadata
    {track name}_logo.png   — embedded venue logo (if present)
"""

import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Reuse parsing and SVG functions from tkk_to_svg.py
import tkk_to_svg


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------

def _null_str(buf: bytes, offset: int = 0, max_len: int | None = None) -> str:
    chunk = buf[offset:] if max_len is None else buf[offset:offset + max_len]
    end = chunk.find(b"\x00")
    return chunk[:end].decode("utf-8", errors="replace") if end != -1 else chunk.decode("utf-8", errors="replace")


def extract_metadata(chunks: dict[str, bytes]) -> dict:
    meta = {}

    # --- Ptkk: full track name + venue ID ---
    if "Ptkk" in chunks:
        ptkk = chunks["Ptkk"]
        meta["name"] = _null_str(ptkk, 4)           # full name, e.g. "Rudskogen Motorsenter AS"
        # Venue ID is the last 8 ASCII chars before end of body
        tail = ptkk.rstrip(b"\x00")
        meta["venue_id"] = tail[-8:].decode("ascii", errors="replace") if len(tail) >= 8 else ""

    # --- Vnfo: short name, country, reference coords, track length ---
    if "Vnfo" in chunks:
        vnfo = chunks["Vnfo"]
        meta["short_name"] = _null_str(vnfo, 0, 28)
        meta["country"]    = _null_str(vnfo, 28, 4)
        if len(vnfo) >= 48:
            length_m = struct.unpack_from("<f", vnfo, 44)[0]
            if length_m > 0:
                meta["track_length_m"] = round(length_m, 1)
        if len(vnfo) >= 60:
            lat, lon, alt = struct.unpack_from("<iii", vnfo, 48)
            meta["reference_point"] = {"lat": lat / 1e7, "lon": lon / 1e7, "alt_m": alt / 1000}
        if len(vnfo) >= 92:
            lat, lon, _ = struct.unpack_from("<iii", vnfo, 80)
            meta["start_finish"] = {"lat": lat / 1e7, "lon": lon / 1e7}

    # --- srfs: surface type ---
    _surface_map = {1: "asphalt", 2: "dirt", 4: "ice", 16: "gravel"}
    if "srfs" in chunks and len(chunks["srfs"]) >= 4:
        srfs_val = struct.unpack_from("<I", chunks["srfs"])[0]
        meta["surface"] = _surface_map.get(srfs_val, f"unknown({srfs_val})")

    # --- zots: timezone ---
    if "zots" in chunks:
        zots = chunks["zots"]
        meta["timezone"]       = _null_str(zots, 0, 64)
        meta["timezone_label"] = _null_str(zots, 64, 128)

    # --- plus: address / contact XML ---
    if "plus" in chunks:
        try:
            xml_text = chunks["plus"].decode("utf-8", errors="replace")
            root = ET.fromstring(xml_text)
            addr = {}
            field_map = {
                "Cty": "city", "Adr": "address", "Pco": "postal_code",
                "Tel": "phone",  "Url": "url",
            }
            for p in root.iter("p"):
                key = field_map.get(p.get("n"), p.get("n", ""))
                if key and p.text:
                    addr[key] = p.text.strip()
            meta["contact"] = addr
        except ET.ParseError:
            pass

    return meta


# ---------------------------------------------------------------------------
# Logo extraction
# ---------------------------------------------------------------------------

def extract_logo(chunks: dict[str, bytes]) -> tuple[str, bytes] | None:
    """Return (original_filename, png_bytes) or None if no logo."""
    if "lgo" not in chunks:
        return None
    lgo = chunks["lgo"]
    null_pos = lgo.find(b"\x00")
    if null_pos == -1:
        return None
    filename = lgo[:null_pos].decode("ascii", errors="replace")
    png_bytes = lgo[null_pos + 1:]
    # Sanity-check PNG magic
    if not png_bytes.startswith(b"\x89PNG"):
        return None
    return filename, png_bytes


# ---------------------------------------------------------------------------
# Filename sanitisation
# ---------------------------------------------------------------------------

def safe_filename(name: str) -> str:
    """Turn a track name into a filesystem-safe filename (no extension)."""
    name = name.strip()
    # Replace characters illegal on Windows/macOS/Linux
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    # Collapse multiple spaces/underscores
    name = re.sub(r"[ _]{2,}", " ", name)
    return name.strip(" .")


# ---------------------------------------------------------------------------
# Per-file conversion
# ---------------------------------------------------------------------------

def convert_tkk(tkk_path: Path, out_dir: Path) -> None:
    data = tkk_path.read_bytes()
    chunks = tkk_to_svg.parse_chunks(data)

    if "pts" not in chunks:
        print(f"  SKIP {tkk_path.name}: no 'pts' chunk")
        return

    points = tkk_to_svg.decode_points(chunks["pts"])
    meta   = extract_metadata(chunks)

    track_name  = meta.get("name") or tkk_path.stem
    device_name = meta.get("short_name", "").strip()
    # Only append device name if it adds new information
    if device_name and device_name.lower() not in track_name.lower():
        combined = f"{track_name} {device_name}"
    else:
        combined = track_name
    base_name = safe_filename(combined)

    # --- SVG ---
    svg_path = out_dir / f"{base_name}.svg"
    svg_info = tkk_to_svg.points_to_svg(points, svg_path)

    # --- Logo PNG ---
    logo_result = extract_logo(chunks)
    logo_rel_path = None
    if logo_result:
        _, png_bytes = logo_result
        logo_path = out_dir / f"{base_name}_logo.png"
        logo_path.write_bytes(png_bytes)
        logo_rel_path = logo_path.name
        print(f"  Logo:  {logo_path.name}  ({len(png_bytes)} bytes)")

    # --- JSON ---
    gps_points = [
        {"lat": lat, "lon": lon, "alt_m": alt}
        for lat, lon, alt in points
    ]
    payload = {
        "source_file": tkk_path.name,
        "full_name": base_name,
        **meta,
        **svg_info,
        "logo_file": logo_rel_path,
        "svg_file":  svg_path.name,
        "gps_points": gps_points,
    }
    json_path = out_dir / f"{base_name}.json"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  JSON:  {json_path.name}  ({len(gps_points)} GPS points)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

TKK_DIR = Path(r"C:\python-projects\tracktaxonomy\tkk-convert\tkk-files")
OUT_DIR = Path(r"C:\python-projects\tracktaxonomy\public\alltracks")


def main() -> None:
    tkk_dir = TKK_DIR
    out_dir  = OUT_DIR

    if not tkk_dir.is_dir():
        print(f"ERROR: {tkk_dir} is not a directory")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    tkk_files = sorted(tkk_dir.glob("*.tkk"))
    if not tkk_files:
        print(f"No .tkk files found in {tkk_dir}")
        sys.exit(0)

    print(f"Found {len(tkk_files)} .tkk file(s) in {tkk_dir}")
    print(f"Output directory: {out_dir}\n")

    ok = err = 0
    for tkk_path in tkk_files:
        print(f"[{tkk_path.name}]")
        try:
            convert_tkk(tkk_path, out_dir)
            ok += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            err += 1
        print()

    print(f"Done: {ok} converted, {err} failed.")


if __name__ == "__main__":
    main()
