"""Predicted standing water depth: a simple water balance for a 15-minute design burst.

    excess rain   = max(0, rain intensity - drain capacity)            mm/hr
    runoff volume = C x excess x burst duration x local catchment area  m3
    depth         = runoff volume / pooling area                         m

Inputs and where they come from:
    rain intensity    slider value, or a design storm (core/storms.py, per city)
    drain capacity    the city's documented drain design standard where the road is served (core/cities.py,
                      core/drainage.Drainage.capacity_mm_hr), zero where the official drain map shows no
                      drain near the road.
    C                 0.85, runoff coefficient for paved urban surfaces (standard textbook value)
    catchment area    if the spot sits in a bare-earth hollow: land draining to it (core/hydrology.py),
                      clamped to 0.2-5 ha (above that, runoff is carried away in channels). If only the
                      dashcam sees a dip: the street around it, 1500 m2 (60 m of road x 25 m incl. footpaths),
                      because terrain runoff is not funnelled into a dip the terrain itself does not show
    pooling area      bare-earth hollow footprint within 60 m plus dashcam-measured dip area

Water only stands where something holds it. So:
    in a hollow       the catchment's excess runoff fills it like a bowl (volume grows with depth squared,
                      so depth = hollow depth x sqrt(volume / bowl volume)); once full, the overflow spreads
                      over the surrounding road (at least 900 m2, about 60 m of road x 15 m) and keeps rising
    not in a hollow   only the rain falling on the spot itself lies on the road as a thin sheet
                      (C x excess x burst duration, about 1-2 cm), the rest runs off downhill

Road sags measured by the phone's sensors (core/roadprofile.py; underpasses the 30 m terrain cannot see)
are filled separately from their measured shape: excess runoff from the sag's own ramps, poured into the
profile from its lowest point. The deeper of the two predictions is used.

Sizing the fix (sizing()): the same model run backwards. Find the drain capacity at which the 2-year storm
leaves at most TARGET_DEPTH_M standing, and turn it into the flow the drains must carry away from the area
that feeds the spot (no figure for today's drains is given: their real capacity is not published):

    flow (L/s) = C x capacity (mm/hr) x contributing area (m2) / 3600

It is a screening model: no pipe hydraulics, infiltration, blockage or water flowing between cells.
Each number can be explained and replaced by a better one, which is the point.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .storms import RETURN_PERIODS, nearest_station

RUNOFF_C = 0.85
BURST_HOURS = 0.25
CATCHMENT_MIN_M2, CATCHMENT_MAX_M2 = 2_000.0, 50_000.0
STREET_CATCHMENT_M2 = 1_500.0
HOLLOW_MIN_DEPTH_M = 0.05
SPREAD_MIN_M2 = 900.0
MAX_DEPTH_M = 1.5
CURVE_MM_HR = tuple(range(0, 151, 10))
TARGET_DEPTH_M = 0.05  # "passable": what the fix must achieve in the 2-year storm


def flow_ls(capacity_mm_hr: float, area_m2: float) -> float:
    """Flow (litres per second) that a drain capacity removes from an area, after the runoff coefficient."""
    return RUNOFF_C * capacity_mm_hr * area_m2 / 3600


@dataclass
class WaterBalance:
    catchment_m2: float
    pool_m2: float  # 0 when there is no hollow
    hollow_depth_m: float
    drain_mm_hr: float

    @property
    def in_hollow(self) -> bool:
        return self.pool_m2 > 0 and self.hollow_depth_m >= HOLLOW_MIN_DEPTH_M

    def depth_m(self, rain_mm_hr: float, drain_mm_hr: float | None = None) -> float:
        drain = self.drain_mm_hr if drain_mm_hr is None else drain_mm_hr
        excess_m_hr = max(0.0, rain_mm_hr - drain) / 1000
        sheet = RUNOFF_C * excess_m_hr * BURST_HOURS
        if not self.in_hollow:
            return float(sheet)
        volume = RUNOFF_C * excess_m_hr * BURST_HOURS * self.catchment_m2
        bowl = 0.5 * self.pool_m2 * self.hollow_depth_m  # paraboloid: half the cylinder
        if volume <= bowl:
            depth = self.hollow_depth_m * (volume / bowl) ** 0.5
        else:
            spread = max(SPREAD_MIN_M2, 4 * self.pool_m2)
            depth = self.hollow_depth_m + (volume - bowl) / spread
        return float(min(MAX_DEPTH_M, max(sheet, depth)))


def water_balance(hydro: dict, drain_mm_hr: float, dip_area_m2: float = 0.0, dip_depth_m: float = 0.0) -> WaterBalance:
    """hydro: Hydrology.sample() output for the spot; dip_*: dashcam-measured road dips, if any."""
    dem_hollow = hydro["depressionAreaM2"] > 0 and hydro["depression"] >= HOLLOW_MIN_DEPTH_M
    pool = (hydro["depressionAreaM2"] if dem_hollow else 0.0) + dip_area_m2
    hollow_depth = max(hydro["depression"] if dem_hollow else 0.0, dip_depth_m)
    return WaterBalance(
        catchment_m2=float(np.clip(hydro["upstream"], CATCHMENT_MIN_M2, CATCHMENT_MAX_M2)) if dem_hollow else STREET_CATCHMENT_M2,
        pool_m2=pool,
        hollow_depth_m=hollow_depth,
        drain_mm_hr=drain_mm_hr,
    )


def predict(
    lat: float,
    lng: float,
    hydro: dict,
    drain_mm_hr: float,
    dip_area_m2: float = 0.0,
    dip_depth_m: float = 0.0,
    city_key: str = "delhi",
    sag: Callable[[float], float] | None = None,
    sag_area_m2: float = 0.0,
) -> dict:
    """Depths for design storms at the nearest rain station, plus a depth-vs-rain curve for the UI slider.
    sag: optional road-sag filler, excess runoff (mm) -> water depth (m), from core/roadprofile.py."""
    wb = water_balance(hydro, drain_mm_hr, dip_area_m2, dip_depth_m)
    station = nearest_station(lat, lng, city_key)

    def parts(rain: float, drain: float | None = None) -> tuple[float, float]:
        """(terrain/dip depth, road-sag depth) in metres."""
        drain = wb.drain_mm_hr if drain is None else drain
        sag_d = 0.0
        if sag is not None:
            sag_d = min(MAX_DEPTH_M, sag(RUNOFF_C * max(0.0, rain - drain) * BURST_HOURS))
        return wb.depth_m(rain, drain), sag_d

    def depth_m(rain: float, drain: float | None = None) -> float:
        return max(parts(rain, drain))

    storm2 = station.intensity(RETURN_PERIODS[0])

    return {
        "station": station.name,
        "drainCapacityMmHr": round(wb.drain_mm_hr, 1),
        "catchmentM2": round(wb.catchment_m2),
        "poolM2": round(wb.pool_m2),
        "inHollow": wb.in_hollow,
        "hollowDepthCm": round(wb.hollow_depth_m * 100, 1),
        "designStorms": [
            {"returnPeriodYears": t, "rainMmHr": round(station.intensity(t), 1), "depthCm": round(depth_m(station.intensity(t)) * 100, 1)}
            for t in RETURN_PERIODS
        ],
        "curve": {"rainMmHr": list(CURVE_MM_HR), "depthCm": [round(depth_m(r) * 100, 1) for r in CURVE_MM_HR]},
        "sizing": sizing(wb, parts, depth_m, storm2, sag_area_m2),
    }


def sizing(wb: WaterBalance, parts, depth_m, rain: float, sag_area_m2: float) -> dict:
    """Drain capacity needed to keep the 2-year storm below TARGET_DEPTH_M, as flows in L/s."""
    terrain, sag = parts(rain)
    governs = "sag" if sag >= terrain and sag > 0 else ("hollow" if wb.in_hollow else "sheet")
    area = sag_area_m2 if governs == "sag" else wb.catchment_m2
    out = {
        "targetCm": round(TARGET_DEPTH_M * 100),
        "rainMmHr": round(rain, 1),
        "governs": governs,
        "areaM2": round(area),
        "designMmHr": round(wb.drain_mm_hr, 1),
        "requiredMmHr": None,
        "requiredLs": None,
    }
    if depth_m(rain) <= TARGET_DEPTH_M:
        return out  # already passable: no fix needed
    lo, hi = wb.drain_mm_hr, rain  # at capacity == rain nothing is left over, so the answer is in range
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if depth_m(rain, mid) > TARGET_DEPTH_M else (lo, mid)
    out["requiredMmHr"] = round(hi, 1)
    out["requiredLs"] = round(flow_ls(hi, area))
    return out
