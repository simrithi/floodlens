"""Combining frame findings, terrain and rainfall into a 0-100 waterlogging risk per road cell.

Version 0 heuristic. Each factor is scaled to 0..1, then weighted:

    terrain   0.35  lower than the surrounding 400 m (DEM)      -2.5 m or lower -> 1
    surface   0.25  depth and extent of road dips (dashcam)       8 cm / 6 m2 -> 1
    potholes  0.15  pothole area and count (dashcam)              2 m2 or ~7 potholes -> 1
    kerb      0.10  road sitting below the kerb (dashcam)         5..20 cm -> 0..1
    rain      0.15  local heavy-rain intensity (ERA5 history)     20 mm/hr p99 -> 1

The weights are a starting point to be tuned against known hotspots, not a calibrated model.
"""

from dataclasses import dataclass, field

import numpy as np

from .elevation import Dem

WEIGHTS = {"terrain": 0.35, "surface": 0.25, "potholes": 0.15, "kerb": 0.10, "rain": 0.15}


def _clip(v: float) -> float:
    return float(np.clip(v, 0.0, 1.0))


def distance_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat = np.radians((a[0] + b[0]) / 2)
    dy = (b[0] - a[0]) * 111_320
    dx = (b[1] - a[1]) * 111_320 * np.cos(lat)
    return float(np.hypot(dx, dy))


@dataclass
class Cell:
    id: str
    segment: str
    start_m: float
    frames: list[dict] = field(default_factory=list)

    def summary(self, dem: Dem, rain_p99: float) -> dict:
        lat = float(np.mean([f["lat"] for f in self.frames]))
        lng = float(np.mean([f["lng"] for f in self.frames]))
        potholes = [p for f in self.frames for p in f["potholes"]]
        dips = [d for f in self.frames for d in f["dips"]]
        kerbs = [f["kerb"]["dropCm"] for f in self.frames if f["kerb"]]

        pothole_area = sum(p["areaM2"] for p in potholes)
        max_dip = max((d["depthCm"] for d in dips), default=0.0)
        dip_area = sum(d["areaM2"] for d in dips) / max(1, len(self.frames))  # mean per frame, frames overlap
        kerb = float(np.median(kerbs)) if kerbs else None
        elevation = dem.elevation(lat, lng)
        relative = dem.relative(lat, lng)

        factors = {
            "terrain": _clip(-relative / 2.5),
            "surface": 0.6 * _clip(max_dip / 8) + 0.4 * _clip(dip_area / 6),
            "potholes": _clip(pothole_area / 2 + len(potholes) * 0.15),
            "kerb": _clip(((kerb or 0) - 5) / 15),
            "rain": _clip(rain_p99 / 20),
        }
        risk = round(100 * sum(WEIGHTS[k] * v for k, v in factors.items()))
        return {
            "id": self.id,
            "segment": self.segment,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "startM": round(self.start_m),
            "frameIndexes": [f["index"] for f in self.frames],
            "potholes": len(potholes),
            "potholeAreaM2": round(pothole_area, 2),
            "maxDipCm": round(max_dip, 1),
            "dipAreaM2": round(dip_area, 2),
            "kerbDropCm": round(kerb, 1) if kerb is not None else None,
            "demElevationM": round(elevation, 1),
            "demRelativeM": round(relative, 2),
            "factors": {k: round(v, 3) for k, v in factors.items()},
            "risk": int(risk),
        }


def build_cells(frames: list[dict], cell_m: float = 60) -> list[Cell]:
    """Group consecutive frames of each segment into ~cell_m stretches of road."""
    cells: list[Cell] = []
    by_segment: dict[str, list[dict]] = {}
    for f in frames:
        by_segment.setdefault(f["segment"], []).append(f)
    for segment, items in by_segment.items():
        items.sort(key=lambda f: f["index"])
        travelled = 0.0
        prev = None
        current: Cell | None = None
        for f in items:
            if prev is not None:
                travelled += distance_m((prev["lat"], prev["lng"]), (f["lat"], f["lng"]))
            if current is None or travelled - current.start_m >= cell_m:
                current = Cell(id=f"{segment}-{len([c for c in cells if c.segment == segment]):02d}", segment=segment, start_m=travelled)
                cells.append(current)
            current.frames.append(f)
            prev = f
    return cells
