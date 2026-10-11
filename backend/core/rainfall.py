"""Rainfall history from the Open-Meteo archive (ERA5 reanalysis), cached on disk."""

import json
from datetime import date

import numpy as np
import requests

from .config import GEO_DIR

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DELHI = (28.6315, 77.2167)
MONSOON_MONTHS = {6, 7, 8, 9}


def hourly_history(lat: float = DELHI[0], lng: float = DELHI[1], start: str = "2021-01-01", end: str = "2025-12-31") -> dict:
    """Hourly precipitation (mm) for a point. Downloaded once, then read from data/geo/."""
    path = GEO_DIR / f"rain_{lat:.3f}_{lng:.3f}_{start}_{end}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    params = {
        "latitude": lat,
        "longitude": lng,
        "start_date": start,
        "end_date": end,
        "hourly": "precipitation",
        "timezone": "Asia/Kolkata",
    }
    r = requests.get(ARCHIVE_URL, params=params, timeout=120)
    r.raise_for_status()
    data = r.json()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def rainfall_stats(lat: float = DELHI[0], lng: float = DELHI[1]) -> dict:
    """Monsoon summary per year plus extremes used by the risk score."""
    data = hourly_history(lat, lng)
    times = data["hourly"]["time"]
    mm = np.array([v if v is not None else 0.0 for v in data["hourly"]["precipitation"]], dtype=float)
    years: dict[int, dict] = {}
    for t, v in zip(times, mm):
        d = date.fromisoformat(t[:10])
        y = years.setdefault(d.year, {"monsoonTotalMm": 0.0, "maxHourlyMm": 0.0, "heavyHours": 0})
        if d.month in MONSOON_MONTHS:
            y["monsoonTotalMm"] += v
        y["maxHourlyMm"] = max(y["maxHourlyMm"], v)
        if v >= 10:
            y["heavyHours"] += 1
    for y in years.values():
        y["monsoonTotalMm"] = round(y["monsoonTotalMm"], 1)
        y["maxHourlyMm"] = round(y["maxHourlyMm"], 1)
    wet = mm[mm > 0.1]
    return {
        "source": "Open-Meteo archive (ERA5 reanalysis), hourly precipitation",
        "point": {"lat": lat, "lng": lng},
        "years": {str(k): v for k, v in sorted(years.items())},
        "maxHourlyMm": round(float(mm.max()), 1),
        "p99WetHourMm": round(float(np.percentile(wet, 99)), 1) if wet.size else 0.0,
        "note": "ERA5 is a ~25 km grid and smooths out short cloudbursts; real peaks are higher.",
    }
