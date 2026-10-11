"""Waterlogging risk per ~60 m road cell (version 1: physical water depth).

The risk is the predicted standing water at a 2-year design storm (core/waterdepth.py), scaled so that
30 cm, the depth at which two-wheelers become unsafe, maps to 100:

    risk = 100 x min(1, depth_2yr_cm / 30)

Inputs per cell: bare-earth hollow and catchment (core/hydrology.py), distance to the nearest mapped
drain (core/drainage.py), dashcam dips (largest depth, mean area per frame), the road sag measured by the
phone's sensors where a sensor log exists (core/roadprofile.py) and the nearest rain station's design
storms (core/storms.py). Version 0 (hand-weighted factors) was replaced after
validation showed its terrain factor barely separated reported hotspots from ordinary roads.

`factors` (0..1) explain the inputs in the UI; they are not weights.
"""

from dataclasses import dataclass, field

import numpy as np

from .drainage import Drainage
from .elevation import Dem
from .hydrology import Hydrology
from .roadprofile import CATCH_WIDTH_M, STEP_M, Profile, frame_index
from .waterdepth import predict

UNSAFE_DEPTH_CM = 30.0
SAG_MIN_M = 1.0  # phone-measured sags shallower than this are within the profile's noise


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

    def summary(self, dem: Dem, hydro: Hydrology, drains: Drainage, city_key: str = "delhi", profile: Profile | None = None) -> dict:
        lat = float(np.mean([f["lat"] for f in self.frames]))
        lng = float(np.mean([f["lng"] for f in self.frames]))
        potholes = [p for f in self.frames for p in f["potholes"]]
        dips = [d for f in self.frames for d in f["dips"]]
        kerbs = [k["dropCm"] for f in self.frames for k in f.get("kerbs", []) if k["dropCm"] is not None]
        kerb_frames = sum(1 for f in self.frames if f.get("kerbs"))

        pothole_area = sum(p["areaM2"] for p in potholes)
        max_dip = max((d["depthCm"] for d in dips), default=0.0)
        dip_area = sum(d["areaM2"] for d in dips) / max(1, len(self.frames))  # mean per frame, frames overlap
        kerb = float(np.median(kerbs)) if kerbs else None
        elevation = dem.elevation(lat, lng)
        relative = dem.relative(lat, lng)

        hyd = hydro.sample(lat, lng)
        drain = drains.nearest(lat, lng)
        # Deepest phone-measured road sag among this stretch's frames.
        sag_i = None
        if profile is not None:
            idx = [i for i in (frame_index(profile, f["index"]) for f in self.frames) if i is not None]
            sag_i = max(idx, key=lambda i: profile.sag_m[i], default=None)
            if sag_i is not None and profile.sag_m[sag_i] < SAG_MIN_M:
                sag_i = None
        road_sag = None
        sag_area = 0.0
        if sag_i is not None:
            a, b = profile.basin(sag_i)
            road_sag = {"depthM": round(float(profile.sag_m[sag_i]), 2), "lengthM": round((b - a + 1) * STEP_M)}
            sag_area = (b - a + 1) * STEP_M * CATCH_WIDTH_M
        water = predict(
            lat,
            lng,
            hyd,
            drains.capacity_mm_hr(drain["distanceM"]),
            dip_area_m2=dip_area + pothole_area,
            dip_depth_m=max_dip / 100,
            city_key=city_key,
            sag=(lambda excess_mm, i=sag_i: profile.water_depth_m(i, excess_mm)) if sag_i is not None else None,
            sag_area_m2=sag_area,
        )
        depth_2y = water["designStorms"][0]["depthCm"]
        storm_2y = water["designStorms"][0]["rainMmHr"]

        factors = {
            "terrain": _clip(hyd["depression"] / 0.5),  # bare-earth hollow, 50 cm deep -> 1
            "sag": _clip((road_sag or {}).get("depthM", 0.0) / 3),  # phone-measured road sag, 3 m deep -> 1
            "surface": 0.6 * _clip(max_dip / 8) + 0.4 * _clip(dip_area / 6),  # dashcam dips
            "potholes": _clip(pothole_area / 2 + len(potholes) * 0.15),
            "drainage": _clip((drain["distanceM"] - 150) / 650),  # far from a mapped drain -> 1
            "rain": _clip((storm_2y - water["drainCapacityMmHr"]) / 100),  # 2-year burst above drain capacity
        }
        risk = round(100 * min(1.0, depth_2y / UNSAFE_DEPTH_CM))
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
            "kerbFrames": kerb_frames,
            "demElevationM": round(elevation, 1),
            "demRelativeM": round(relative, 2),
            "dem": dem.kind,
            "hollowDepthCm": round(hyd["depression"] * 100, 1),
            "roadSag": road_sag,
            "catchmentM2": round(hyd["upstream"]),
            "drain": {"distanceM": round(drain["distanceM"]), "class": drain["class"], "name": drain["name"], "covered": drain["tunnel"]},
            "water": water,
            "depth2yCm": depth_2y,
            "factors": {k: round(v, 3) for k, v in factors.items()},
            "risk": int(risk),
        }


RAMP_MAX_M = 400.0  # a stretch this far from a sag's bottom is not reported as its ramp


def link_ramps(cells: list[dict], profile: Profile | None) -> None:
    """Mark stretches whose runoff ends in a phone-measured sag elsewhere (the ramps into an underpass).

    A stretch drains into sag j if it lies on j's ramps: the road rises steadily from j's bottom to it
    (Profile.ramps), so water starting there runs down into j, even from above the rim. Adds cell["drainsTo"] = {id, distanceM, ahead, depth2yCm, sagM} or None."""
    for c in cells:
        c["drainsTo"] = None
    if profile is None:
        return
    points = {c["id"]: [i for i in (frame_index(profile, k) for k in c["frameIndexes"]) if i is not None] for c in cells}
    sags = [c for c in cells if c.get("roadSag") and points[c["id"]]]
    bottoms = {c["id"]: max(points[c["id"]], key=lambda i: profile.sag_m[i]) for c in sags}
    for c in cells:
        if c.get("roadSag") or not points[c["id"]]:
            continue
        i = points[c["id"]][len(points[c["id"]]) // 2]
        best = None
        for s in sags:
            j = bottoms[s["id"]]
            a, b = profile.ramps(j, RAMP_MAX_M)
            gap = float(profile.distance_m[j] - profile.distance_m[i])
            if a <= i <= b and abs(gap) <= RAMP_MAX_M and profile.elevation_m[i] > profile.elevation_m[j]:
                if best is None or profile.sag_m[j] > profile.sag_m[bottoms[best[0]["id"]]]:
                    best = (s, gap)
        if best:
            s, gap = best
            c["drainsTo"] = {
                "id": s["id"],
                "distanceM": round(abs(gap) / 10) * 10,
                "ahead": gap > 0,
                "depth2yCm": s["depth2yCm"],
                "sagM": s["roadSag"]["depthM"],
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
