"""DXF -> G-code conversion for CNC plasma cutting (targets WinCNC-style controllers,
e.g. ShopSabre: M3/M5 torch control, G4 pierce dwell, plain G0/G1 motion)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import ezdxf
from shapely.geometry import Polygon

EPS = 1e-6
CUTTABLE_TYPES = {"LINE", "ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE"}


@dataclass
class Settings:
    units: str = "mm"                 # "mm" or "in"
    kerf_width: float = 1.0           # total kerf width, in drawing units
    pierce_delay: float = 0.4         # seconds
    lead_in_length: float = 3.0
    lead_out_length: float = 3.0
    segment_tolerance: float = 0.05   # max sagitta when flattening arcs/splines
    normalize_origin: bool = True
    layers: list[str] | None = None   # None = all layers


@dataclass
class Path:
    points: list[tuple[float, float]]
    closed: bool
    depth: int = 0
    area: float = 0.0


class ConversionError(Exception):
    pass


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _round_key(p, precision=4):
    return (round(p[0], precision), round(p[1], precision))


def _entity_points(entity, tolerance):
    """Return an ordered list of (x, y) points approximating a single DXF entity."""
    dxftype = entity.dxftype()
    if dxftype == "LINE":
        start, end = entity.dxf.start, entity.dxf.end
        return [(start.x, start.y), (end.x, end.y)]
    if dxftype in ("LWPOLYLINE", "POLYLINE"):
        pts = []
        for sub in entity.virtual_entities():
            sub_pts = _entity_points(sub, tolerance)
            if not sub_pts:
                continue
            if pts and _dist(pts[-1], sub_pts[0]) < 1e-6:
                sub_pts = sub_pts[1:]
            pts.extend(sub_pts)
        return pts
    if hasattr(entity, "flattening"):
        return [(p.x, p.y) for p in entity.flattening(tolerance)]
    return []


def load_raw_segments(doc, settings: Settings):
    msp = doc.modelspace()
    segments = []
    for entity in msp:
        if entity.dxftype() not in CUTTABLE_TYPES:
            continue
        if settings.layers and entity.dxf.layer not in settings.layers:
            continue
        try:
            pts = _entity_points(entity, settings.segment_tolerance)
        except Exception:
            continue
        if len(pts) < 2:
            continue
        segments.append(pts)
    return segments


def chain_segments(segments):
    """Greedily join open polyline segments that share endpoints into longer paths."""
    remaining = [list(seg) for seg in segments]
    paths: list[Path] = []

    while remaining:
        chain = remaining.pop(0)
        changed = True
        while changed:
            changed = False
            for i, seg in enumerate(remaining):
                if _dist(chain[-1], seg[0]) < 1e-3:
                    chain.extend(seg[1:])
                    remaining.pop(i)
                    changed = True
                    break
                if _dist(chain[-1], seg[-1]) < 1e-3:
                    chain.extend(list(reversed(seg))[1:])
                    remaining.pop(i)
                    changed = True
                    break
                if _dist(chain[0], seg[-1]) < 1e-3:
                    chain = seg[:-1] + chain
                    remaining.pop(i)
                    changed = True
                    break
                if _dist(chain[0], seg[0]) < 1e-3:
                    chain = list(reversed(seg))[:-1] + chain
                    remaining.pop(i)
                    changed = True
                    break
        closed = _dist(chain[0], chain[-1]) < 1e-3
        if closed and chain[0] != chain[-1]:
            chain[-1] = chain[0]
        paths.append(Path(points=chain, closed=closed))
    return paths


def _shoelace_area(points):
    n = len(points)
    a = 0.0
    for i in range(n - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        a += x1 * y2 - x2 * y1
    return a / 2.0


def _point_in_poly(pt, poly_points):
    x, y = pt
    inside = False
    n = len(poly_points)
    j = n - 1
    for i in range(n):
        xi, yi = poly_points[i]
        xj, yj = poly_points[j]
        if ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or EPS) + xi
        ):
            inside = not inside
        j = i
    return inside


def compute_nesting(paths: list[Path]):
    closed_paths = [p for p in paths if p.closed]
    for p in closed_paths:
        p.area = abs(_shoelace_area(p.points))
    for p in closed_paths:
        test_pt = p.points[0]
        depth = 0
        for other in closed_paths:
            if other is p:
                continue
            if other.area <= p.area:
                continue
            if _point_in_poly(test_pt, other.points):
                depth += 1
        p.depth = depth


def apply_kerf(paths: list[Path], settings: Settings):
    if settings.kerf_width <= 0:
        return paths
    half = settings.kerf_width / 2.0
    out = []
    for p in paths:
        if not p.closed:
            out.append(p)
            continue
        try:
            poly = Polygon(p.points)
            if not poly.is_valid:
                poly = poly.buffer(0)
            sign = 1 if p.depth % 2 == 0 else -1
            offset = poly.buffer(sign * half, join_style=2)
            if offset.is_empty:
                out.append(p)
                continue
            geom = max(offset.geoms, key=lambda g: g.area) if offset.geom_type == "MultiPolygon" else offset
            coords = list(geom.exterior.coords)
            new_path = Path(points=coords, closed=True, depth=p.depth, area=p.area)
            out.append(new_path)
        except Exception:
            out.append(p)
    return out


def order_paths(paths: list[Path]):
    closed = sorted([p for p in paths if p.closed], key=lambda p: p.area)
    open_paths = [p for p in paths if not p.closed]
    return closed + open_paths


def normalize(paths: list[Path]):
    xs = [x for p in paths for x, y in p.points]
    ys = [y for p in paths for x, y in p.points]
    if not xs:
        return paths
    min_x, min_y = min(xs), min(ys)
    for p in paths:
        p.points = [(x - min_x, y - min_y) for x, y in p.points]
    return paths


def _lead_vector(p1, p2, length):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    d = math.hypot(dx, dy) or 1.0
    return (dx / d * length, dy / d * length)


def build_gcode(paths: list[Path], settings: Settings) -> str:
    lines = []
    unit_cmd = "G21" if settings.units == "mm" else "G20"
    lines.append("(Generated by dxftogcode)")
    lines.append(unit_cmd)
    lines.append("G90")
    lines.append("G17")

    for path in paths:
        pts = path.points
        if len(pts) < 2:
            continue

        if path.closed:
            start = pts[0]
            lead_dx, lead_dy = _lead_vector(pts[1], pts[0], settings.lead_in_length)
            lead_in_pt = (start[0] - lead_dx, start[1] - lead_dy)
            end_dx, end_dy = _lead_vector(pts[-2], pts[-1], settings.lead_out_length)
            lead_out_pt = (pts[-1][0] + end_dx, pts[-1][1] + end_dy)
            cut_points = pts + [lead_out_pt]
            entry_pt = lead_in_pt
        else:
            entry_pt = pts[0]
            cut_points = pts

        lines.append(f"G0 X{entry_pt[0]:.4f} Y{entry_pt[1]:.4f}")
        lines.append("M3")
        if settings.pierce_delay > 0:
            lines.append(f"G4 P{settings.pierce_delay:.3f}")
        for x, y in cut_points:
            lines.append(f"G1 X{x:.4f} Y{y:.4f}")
        lines.append("M5")

    lines.append("G0 X0 Y0")
    lines.append("M30")
    return "\n".join(lines) + "\n"


def convert(dxf_path: str, settings: Settings) -> str:
    try:
        doc = ezdxf.readfile(dxf_path)
    except IOError as e:
        raise ConversionError(f"Could not read DXF file: {e}")
    except ezdxf.DXFStructureError as e:
        raise ConversionError(f"Invalid DXF file: {e}")

    segments = load_raw_segments(doc, settings)
    if not segments:
        raise ConversionError("No cuttable geometry found (LINE/ARC/CIRCLE/POLYLINE/SPLINE).")

    paths = chain_segments(segments)
    compute_nesting(paths)
    paths = apply_kerf(paths, settings)
    paths = order_paths(paths)
    if settings.normalize_origin:
        paths = normalize(paths)

    return build_gcode(paths, settings)
