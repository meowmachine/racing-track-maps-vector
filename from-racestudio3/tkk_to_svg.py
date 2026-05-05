#!/usr/bin/env python3
"""
tkk_to_svg.py — Extract GPS track map from RaceStudio 3 .tkk file and write SVG.

TKK format: sequence of chunks, each with a 12-byte header:
  <h + 4-byte-name (null-padded) + 4-byte-LE uint32 size + 0x00 + >
followed by <size> bytes of data, then an 8-byte closing tag.

The 'pts ' chunk holds GPS points as 12-byte records:
  int32 LE  latitude  * 10_000_000
  int32 LE  longitude * 10_000_000
  int32 LE  altitude  in millimetres (0 on the start/finish sentinel)
"""

import struct
import sys
import math
from pathlib import Path


# ---------------------------------------------------------------------------
# TKK parser
# ---------------------------------------------------------------------------

def parse_chunks(data: bytes) -> dict[str, bytes]:
    """Return mapping of chunk name -> raw body bytes."""
    chunks = {}
    i = 0
    while i < len(data):
        if data[i : i + 2] != b"<h":
            i += 1
            continue
        # Name: 4 bytes (null-padded), size: 4-byte LE uint32, then 0x00 + >
        if i + 12 > len(data):
            break
        name = data[i + 2 : i + 6].rstrip(b"\x00").decode("ascii", errors="replace")
        size = struct.unpack_from("<I", data, i + 6)[0]
        body_start = i + 12
        body = data[body_start : body_start + size]
        chunks[name] = body
        i = body_start + size + 8  # skip body + closing tag
    return chunks


# ---------------------------------------------------------------------------
# GPS point decoder
# ---------------------------------------------------------------------------

def decode_points(pts_body: bytes) -> list[tuple[float, float, float]]:
    """Return list of (lat_deg, lon_deg, alt_m) from the 'pts ' chunk body."""
    record_size = 12
    n = len(pts_body) // record_size
    points = []
    for i in range(n):
        lat_raw, lon_raw, alt_mm = struct.unpack_from("<iii", pts_body, i * record_size)
        points.append((lat_raw / 1e7, lon_raw / 1e7, alt_mm / 1000.0))
    return points


# ---------------------------------------------------------------------------
# SVG builder
# ---------------------------------------------------------------------------

def _unproject(x: float, y: float,
               lat0: float, lon0: float,
               scale: float) -> tuple[float, float]:
    """Inverse of _project: screen coords back to (lat, lon)."""
    lat = lat0 - y / (111_320 * scale)
    lon = lon0 + x / (111_320 * math.cos(math.radians(lat0)) * scale)
    return lat, lon


def _project(lat: float, lon: float,
             lat0: float, lon0: float,
             scale: float) -> tuple[float, float]:
    """
    Simple equirectangular projection centred on (lat0, lon0).
    Returns (x, y) in the same unit as scale (metres per degree * scale).
    """
    # 1 degree latitude ≈ 111_320 m; longitude degree shrinks by cos(lat)
    x = (lon - lon0) * 111_320 * math.cos(math.radians(lat0)) * scale
    y = -(lat - lat0) * 111_320 * scale   # flip y so north is up
    return x, y


def _catmull_rom_to_bezier(p0: tuple, p1: tuple, p2: tuple, p3: tuple,
                           alpha: float = 0.5) -> tuple:
    """
    Return the two cubic bezier control points (cp1, cp2) for the segment
    p1→p2, using a Catmull-Rom parameterisation with tension alpha.
    """
    def tj(ti, pi, pj):
        dx, dy = pj[0] - pi[0], pj[1] - pi[1]
        return ti + (dx * dx + dy * dy) ** (alpha / 2)

    t0 = 0.0
    t1 = tj(t0, p0, p1)
    t2 = tj(t1, p1, p2)
    t3 = tj(t2, p2, p3)

    if t1 == t0 or t2 == t1 or t3 == t2:
        return p1, p2

    def lerp(a, b, ta, tb, t):
        s = (t - ta) / (tb - ta)
        return (a[0] + s * (b[0] - a[0]), a[1] + s * (b[1] - a[1]))

    def lerpv(u, v, t):
        return (u[0] + t * (v[0] - u[0]), u[1] + t * (v[1] - u[1]))

    a1 = lerp(p0, p1, t0, t1, t1)   # p1
    a2 = lerp(p1, p2, t1, t2, t1)
    a3 = lerp(p2, p3, t2, t3, t1)
    b1 = lerp(a1, a2, t0, t2, t1)   # p1
    b2 = lerp(a2, a3, t1, t3, t1)

    a1e = lerp(p0, p1, t0, t1, t2)
    a2e = lerp(p1, p2, t1, t2, t2)
    a3e = lerp(p2, p3, t2, t3, t2)
    b1e = lerp(a1e, a2e, t0, t2, t2)
    b2e = lerp(a2e, a3e, t1, t3, t2)

    cp1 = (b1[0] + (t2 - t1) / 3 * (b2[0] - b1[0]) / (t2 - t0) * 3,
           b1[1] + (t2 - t1) / 3 * (b2[1] - b1[1]) / (t2 - t0) * 3)
    cp2 = (b1e[0] - (t2 - t1) / 3 * (b2e[0] - b1e[0]) / (t3 - t1) * 3,
           b1e[1] - (t2 - t1) / 3 * (b2e[1] - b1e[1]) / (t3 - t1) * 3)

    # Simpler and more robust: use the classic Barry-Goldman formula
    # cp1 for segment p1→p2:
    cp1 = (p1[0] + (p2[0] - p0[0]) * (t2 - t1) / (6 * (t2 - t0)),
           p1[1] + (p2[1] - p0[1]) * (t2 - t1) / (6 * (t2 - t0)))
    cp2 = (p2[0] - (p3[0] - p1[0]) * (t2 - t1) / (6 * (t3 - t1)),
           p2[1] - (p3[1] - p1[1]) * (t2 - t1) / (6 * (t3 - t1)))
    return cp1, cp2


def _smooth_path(xy: list[tuple[float, float]]) -> str:
    """
    Build a smooth closed SVG cubic-bezier path through the given points
    using a centripetal Catmull-Rom spline.
    """
    n = len(xy)
    # Wrap-around neighbours for a closed loop
    def pt(i):
        return xy[i % n]

    d = f"M {xy[0][0]:.2f},{xy[0][1]:.2f} "
    for i in range(n):
        p0, p1, p2, p3 = pt(i - 1), pt(i), pt(i + 1), pt(i + 2)
        cp1, cp2 = _catmull_rom_to_bezier(p0, p1, p2, p3)
        d += (f"C {cp1[0]:.2f},{cp1[1]:.2f} "
              f"{cp2[0]:.2f},{cp2[1]:.2f} "
              f"{p2[0]:.2f},{p2[1]:.2f} ")
    d += "Z"
    return d


def points_to_svg(points: list[tuple[float, float, float]],
                  output_path: Path,
                  padding: float = 40.0,
                  target_size: float = 800.0,
                  stroke_width: float = 8.0) -> dict:
    """
    Write an SVG file with track outline and start/finish line.
    Returns a dict with the start/finish line GPS endpoints.
    """

    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    lat0 = (min(lats) + max(lats)) / 2
    lon0 = (min(lons) + max(lons)) / 2

    # Choose scale so the longer axis fits in target_size px
    dlat = (max(lats) - min(lats)) * 111_320
    dlon = (max(lons) - min(lons)) * 111_320 * math.cos(math.radians(lat0))
    span = max(dlat, dlon)
    scale = (target_size - 2 * padding) / span if span > 0 else 1.0

    xy = [_project(lat, lon, lat0, lon0, scale) for lat, lon, _ in points]

    xs = [p[0] for p in xy]
    ys = [p[1] for p in xy]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Shift so everything is in the positive quadrant with padding
    ox = -min_x + padding
    oy = -min_y + padding
    width  = max_x - min_x + 2 * padding
    height = max_y - min_y + 2 * padding

    shifted = [(x + ox, y + oy) for x, y in xy]

    pts_str = " ".join(f"{x:.2f},{y:.2f}" for x, y in shifted)

    # --- Start/finish perpendicular line ---
    # Direction at S/F point (index 0) from its neighbours
    sf_cx, sf_cy = shifted[0]
    prev_x, prev_y = shifted[-2]   # point just before the closing duplicate
    next_x, next_y = shifted[1]
    dx = next_x - prev_x
    dy = next_y - prev_y
    dist = math.hypot(dx, dy)
    if dist > 0:
        dx, dy = dx / dist, dy / dist
    else:
        dx, dy = 1.0, 0.0
    # Perpendicular vector
    px, py = -dy, dx
    sf_line_len = stroke_width * 5
    sf_x1 = sf_cx - px * sf_line_len / 2
    sf_y1 = sf_cy - py * sf_line_len / 2
    sf_x2 = sf_cx + px * sf_line_len / 2
    sf_y2 = sf_cy + py * sf_line_len / 2

    # Convert S/F line endpoints back to GPS (un-shift offset first)
    sf_gps1 = _unproject(sf_x1 - ox, sf_y1 - oy, lat0, lon0, scale)
    sf_gps2 = _unproject(sf_x2 - ox, sf_y2 - oy, lat0, lon0, scale)

    svg = f"""<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{width:.1f}" height="{height:.1f}"
     viewBox="0 0 {width:.1f} {height:.1f}">
  <rect width="100%" height="100%" fill="#1a1a2e"/>
  <!-- Track outline -->
  <polyline points="{pts_str}"
        fill="none"
        stroke="#e94560"
        stroke-width="{stroke_width}"
        stroke-linejoin="round"
        stroke-linecap="round"/>
  <!-- Start/finish line -->
  <line x1="{sf_x1:.2f}" y1="{sf_y1:.2f}" x2="{sf_x2:.2f}" y2="{sf_y2:.2f}"
        stroke="#f5f5f5" stroke-width="{stroke_width * 1.2:.1f}"
        stroke-linecap="round"/>
</svg>
"""
    output_path.write_text(svg, encoding="utf-8")
    print(f"Wrote {output_path}  ({len(shifted)} points, "
          f"{width:.0f}x{height:.0f} px)")

    return {
        "start_finish_line": {
            "p1": {"lat": round(sf_gps1[0], 7), "lon": round(sf_gps1[1], 7)},
            "p2": {"lat": round(sf_gps2[0], 7), "lon": round(sf_gps2[1], 7)},
        }
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: tkk_to_svg.py <input.tkk> [output.svg]")
        sys.exit(1)

    tkk_path = Path(sys.argv[1])
    svg_path = Path(sys.argv[2]) if len(sys.argv) > 2 else tkk_path.with_suffix(".svg")

    data = tkk_path.read_bytes()
    chunks = parse_chunks(data)

    print(f"Chunks found: {list(chunks.keys())}")

    if "pts" not in chunks:
        print("ERROR: no 'pts' chunk found in file")
        sys.exit(1)

    points = decode_points(chunks["pts"])
    print(f"GPS points decoded: {len(points)}")
    print(f"  lat range: {min(p[0] for p in points):.6f} – {max(p[0] for p in points):.6f}")
    print(f"  lon range: {min(p[1] for p in points):.6f} – {max(p[1] for p in points):.6f}")
    print(f"  alt range: {min(p[2] for p in points):.1f} – {max(p[2] for p in points):.1f} m")

    points_to_svg(points, svg_path)


if __name__ == "__main__":
    main()
