"""Turn scored road stretches into findings an official can act on: spots, causes, fixes, priorities.

For one city, reads every analysed survey (data/outputs/<sequence>-lth/analysis.json) and:

1. Groups stretches predicted to hold at least FLAG_CM of water in the 2-year storm into spots: stretches
   within JOIN_M of each other, across driving directions and surveys, are the same place.
2. Names each spot (a reported waterlogging spot nearby, else OpenStreetMap's name for the road there).
3. Diagnoses the cause from the evidence that is present:
     channel   a mapped channel draining a large area crosses the road at a low point
     sag       the road dips (phone sensors): underpass or sag with nowhere for water to go
     hollow    the road sits in a bare-earth hollow, the nearest mapped drain far away
     drain     hollow with a drain nearby that cannot keep up
     dip       dashcam-measured dips in the road surface
4. Sizes the fix from the water model run backwards (core/waterdepth.sizing): the drainage, in litres per
   second, that keeps the 2-year storm below 5 cm, against what the drains there are assumed to carry.
5. Sets a priority from depth and type (an underpass traps vehicles) and a confidence from how many
   independent kinds of evidence agree.

Writes data/outputs/findings-<city>.json for the UI and the PDF report.

usage: python scripts/build_findings.py --city bengaluru
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cities import CITIES  # noqa: E402
from core.config import BACKEND_DIR, OUTPUTS_DIR  # noqa: E402
from core.elevation import dem  # noqa: E402
from core.frames import sequence_dir  # noqa: E402
from core.roadprofile import STEP_M, build_profile, frame_index  # noqa: E402
from core.score import distance_m  # noqa: E402
from core.storms import STORM_SOURCES  # noqa: E402

FLAG_CM = 5.0  # less than this in the 2-year storm is not a finding
JOIN_M = 250.0
REPORTED_M = 250.0
CHANNEL_M = 100.0
CHANNEL_HA = 50.0
FAR_DRAIN_M = 500.0
PROFILE_SPAN_M = 350.0

CAUSES = {
    "channel": "Low point where a channel crosses the road",
    "sag": "Low point in the road: water has nowhere to go",
    "hollow": "Road in a natural hollow, far from any drain",
    "drain": "Hollow next to a drain that cannot keep up",
    "dip": "Dips in the road surface",
}


def reference(city: str) -> list[dict]:
    """Publicly reported spots with their first source."""
    path = BACKEND_DIR / "validation" / ("reference_hotspots.geo.json" if city == "delhi" else f"reference_{city}.geo.json")
    if not path.exists():
        return []
    ref = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for h in ref["hotspots"]:
        src = ref["sources"].get(h["sources"][0], {})
        out.append({"name": h["name"], "lat": h["lat"], "lng": h["lng"], "source": src.get("title"), "url": src.get("url")})
    return out


def road_name(lat: float, lng: float, cache: dict) -> str | None:
    """OpenStreetMap's name for the road at a point (Nominatim, cached, 1 request per second)."""
    key = f"{lat:.5f},{lng:.5f}"
    if key not in cache:
        time.sleep(1.1)
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 17},
            headers={"User-Agent": "FloodLens-hackathon/0.1"},
            timeout=30,
        )
        a = r.json().get("address", {}) if r.ok else {}
        area = a.get("suburb") or a.get("neighbourhood") or a.get("quarter") or a.get("city_district")
        name = r.json().get("name") if r.ok else None
        cache[key] = ", ".join(x for x in (name, area) if x) or None
    return cache[key]


def surveys(city: str) -> list[dict]:
    out = []
    for path in sorted(OUTPUTS_DIR.glob("*-lth/analysis.json")):
        a = json.loads(path.read_text(encoding="utf-8"))
        if (a.get("city") or {}).get("key", "delhi") == city:
            out.append(a)
    return out


def cluster(cells: list[dict]) -> list[list[dict]]:
    """Single-link groups: stretches within JOIN_M of any member belong together."""
    groups: list[list[dict]] = []
    for c in cells:
        near = [g for g in groups if any(distance_m((c["lat"], c["lng"]), (o["lat"], o["lng"])) <= JOIN_M for o in g)]
        merged = [c]
        for g in near:
            merged += g
            groups.remove(g)
        groups.append(merged)
    return groups


def diagnose(worst: dict) -> str:
    z = worst["water"]["sizing"]
    ha = worst["catchmentM2"] / 1e4
    if worst["drain"]["distanceM"] <= CHANNEL_M and ha >= CHANNEL_HA and (worst.get("roadSag") or worst["hollowDepthCm"] >= 5):
        return "channel"
    if z["governs"] == "sag":
        return "sag"
    if worst["hollowDepthCm"] >= 5:
        return "drain" if worst["drain"]["distanceM"] <= FAR_DRAIN_M else "hollow"
    return "dip"


def fix_text(cause: str, worst: dict, group: list[dict]) -> dict:
    z = worst["water"]["sizing"]
    req = z["requiredLs"]
    d = worst["drain"]
    # Describe the deepest sag measured on any pass, so the text matches the evidence list.
    sag = max((c.get("roadSag") or {} for c in group), key=lambda s: s.get("depthM", 0))
    ha = worst["catchmentM2"] / 1e4
    need = f"Drainage here must remove about {req} L/s to keep a 2-year storm below {z['targetCm']} cm."
    if cause == "channel":
        return {
            "why": f"A channel draining about {ha:,.0f} ha crosses the road {d['distanceM']} m away, at a point where the road dips {sag.get('depthM', 0):.1f} m.",
            "fix": f"Check that the culvert under the road can pass the channel's flood flow, and add road inlets at the low point. {need}",
            "now": "Before the monsoon: desilt the channel and the culvert mouth, clear the road inlets.",
        }
    if cause == "sag":
        return {
            "why": f"The road drops {sag.get('depthM', 0):.1f} m and climbs back out over about {sag.get('lengthM', 0)} m. Rain on {z['areaM2']:,} m² of road and ramps runs to the bottom.",
            "fix": f"Larger inlets at the lowest point, with a sump and pump if there is no gravity outlet. {need}",
            "now": "Before the monsoon: clear the inlets at the bottom, test the pump, plan a diversion for heavy rain.",
        }
    if cause == "hollow":
        return {
            "why": f"The road sits in a {worst['hollowDepthCm']:.0f} cm deep hollow in the land; the nearest mapped drain is {d['distanceM']:,} m away.",
            "fix": f"A new inlet at the hollow with a pipe to the drain {d['distanceM']:,} m away. {need}",
            "now": "Before the monsoon: check for an existing inlet or soakaway and clear it.",
        }
    if cause == "drain":
        return {
            "why": f"The road sits in a {worst['hollowDepthCm']:.0f} cm deep hollow, {d['distanceM']} m from a mapped drain that cannot take the water fast enough.",
            "fix": f"Desilt and, if needed, enlarge the connection to that drain. {need}",
            "now": "Before the monsoon: desilt the drain and its inlets.",
        }
    return {
        "why": f"The dashcam measured a {worst['maxDipCm']:.0f} cm dip in the road surface.",
        "fix": f"Re-level the surface over the dip. {need}",
        "now": "Before the monsoon: patch the dip.",
    }


def priority(cause: str, depth_cm: float) -> str:
    if depth_cm >= 20 or (cause in ("sag", "channel") and depth_cm >= 15):
        return "urgent"
    return "high" if depth_cm >= 10 else "watch"


def profile_slice(profile, frame_idx: int) -> dict | None:
    """Road profile around a sag, for the chart: distance (m), elevation (m), water level at the 2-yr storm."""
    if profile is None:
        return None
    i = frame_index(profile, frame_idx)
    if i is None:
        return None
    # Centre on the deepest point within 150 m.
    w = int(150 / STEP_M)
    lo, hi = max(0, i - w), min(len(profile.sag_m), i + w + 1)
    j = lo + int(profile.sag_m[lo:hi].argmax())
    k = int(PROFILE_SPAN_M / STEP_M)
    a, b = max(0, j - k), min(len(profile.elevation_m), j + k + 1)
    z = profile.elevation_m[a:b]
    return {
        "distanceM": [round(float(profile.distance_m[x] - profile.distance_m[j])) for x in range(a, b)],
        "elevationM": [round(float(v - profile.elevation_m[j]), 2) for v in z],
        "rimM": round(float(profile.level_m[j] - profile.elevation_m[j]), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="bengaluru", choices=sorted(CITIES))
    city = parser.parse_args().city
    runs = surveys(city)
    if not runs:
        raise SystemExit(f"no analysed surveys for {city}")
    refs = reference(city)
    cache_path = CITIES[city].geo_dir / "road_names.json"
    names = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    terrain = dem(city_key=city)

    flagged, frames_by = [], {}
    profiles = {}
    for a in runs:
        seq = a["sequence"]["id"]
        sensors = sequence_dir(seq) / "sensors.txt"
        profiles[seq] = build_profile(sensors, terrain) if sensors.exists() else None
        for f in a["frames"]:
            frames_by[(seq, f["index"])] = f
        for c in a["cells"]:
            if c["depth2yCm"] >= FLAG_CM:
                flagged.append({**c, "_seq": seq, "_segments": {s["name"]: s["label"] for s in a["sequence"]["segments"]}})

    spots = []
    for group in cluster(flagged):
        worst = max(group, key=lambda c: c["depth2yCm"])
        cause = diagnose(worst)
        lat = sum(c["lat"] for c in group) / len(group)
        lng = sum(c["lng"] for c in group) / len(group)
        near = sorted(((distance_m((lat, lng), (r["lat"], r["lng"])), r) for r in refs), key=lambda x: x[0])
        reported = {**near[0][1], "distanceM": round(near[0][0] / 10) * 10} if near and near[0][0] <= REPORTED_M else None
        name = reported["name"] if reported else (road_name(lat, lng, names) or f"{lat:.4f}, {lng:.4f}")
        directions = sorted({c["_segments"].get(c["segment"], c["segment"]) for c in group})
        seq = worst["_seq"]
        frames = [frames_by[(seq, i)] for i in worst["frameIndexes"]]
        best = max(frames, key=lambda f: (f.get("sagM") or 0, len(f["kerbs"])))
        evidence = []
        if len({c["segment"] for c in group}) > 1:
            evidence.append({"kind": "repeat", "text": f"Flagged on {len({c['segment'] for c in group})} separate passes ({len(group)} stretches)"})
        sag = max((c.get("roadSag") or {}).get("depthM", 0) for c in group)
        if sag:
            evidence.append({"kind": "sag", "text": f"Phone sensors: the road dips {sag:.1f} m"})
        hollow = max(c["hollowDepthCm"] for c in group)
        if hollow >= 5:
            evidence.append({"kind": "hollow", "text": f"Satellite elevation: a {hollow:.0f} cm hollow in the land"})
        if worst["catchmentM2"] >= CHANNEL_HA * 1e4:
            evidence.append({"kind": "catchment", "text": f"{worst['catchmentM2'] / 1e4:,.0f} ha of land drains through here"})
        dip = max(c["maxDipCm"] for c in group)
        if dip:
            evidence.append({"kind": "dip", "text": f"Dashcam: a {dip:.0f} cm dip in the road surface"})
        if CITIES[city].official_drains and worst["drain"]["distanceM"] > CITIES[city].served_m:
            evidence.append({"kind": "nodrain", "text": f"Official drain map: no storm drain within {worst['drain']['distanceM']} m"})
        if reported:
            evidence.append({"kind": "reported", "text": f"Reported waterlogged {reported['distanceM']} m away"})
        kinds = {e["kind"] for e in evidence} - {"catchment", "nodrain"}
        confidence = "high" if reported or len(kinds) >= 3 else ("medium" if len(kinds) == 2 else "low")
        depth = worst["depth2yCm"]
        spots.append(
            {
                "name": name,
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "sequence": seq,
                "cells": sorted(c["id"] for c in group),
                "worstCell": worst["id"],
                "directions": directions,
                "cause": cause,
                "causeLabel": CAUSES[cause],
                **fix_text(cause, worst, group),
                "depthCm": {str(s["returnPeriodYears"]): s["depthCm"] for s in worst["water"]["designStorms"]},
                "rainMmHr": {str(s["returnPeriodYears"]): s["rainMmHr"] for s in worst["water"]["designStorms"]},
                "station": worst["water"]["station"],
                "sizing": worst["water"]["sizing"],
                "drain": worst["drain"],
                "evidence": evidence,
                "confidence": confidence,
                "priority": priority(cause, depth),
                "reported": reported,
                "frame": {"index": best["index"], "segment": best["segment"], "overlay": f"{seq}-lth/{best['overlay']}", "image": f"{seq}-lth/{best['image']}"},
                "profile": profile_slice(profiles[seq], best["index"]) if sag else None,
            }
        )
    order = {"urgent": 0, "high": 1, "watch": 2}
    spots.sort(key=lambda s: (order[s["priority"]], -s["depthCm"]["2"]))
    for i, s in enumerate(spots, 1):
        s["id"] = f"S{i}"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(names, indent=1, ensure_ascii=False), encoding="utf-8")

    km = 0.0
    for a in runs:
        by: dict[str, list] = {}
        for f in a["frames"]:
            by.setdefault(f["segment"], []).append(f)
        for fs in by.values():
            fs.sort(key=lambda f: f["index"])
            km += sum(distance_m((p["lat"], p["lng"]), (q["lat"], q["lng"])) for p, q in zip(fs, fs[1:])) / 1000
    out = {
        "city": city,
        "cityName": CITIES[city].name,
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "surveys": [
            {
                "sequence": a["sequence"]["id"],
                "url": a["sequence"]["url"],
                "attribution": a["sequence"]["attribution"],
                "segments": [s["label"] for s in a["sequence"]["segments"]],
                "date": a["frames"][0]["shotDate"][:10],
                "stretches": len(a["cells"]),
                "sensorProfile": a.get("roadProfile") is not None,
            }
            for a in runs
        ],
        "kmFilmed": round(km, 1),
        "stretches": sum(len(a["cells"]) for a in runs),
        "flagCm": FLAG_CM,
        "stormSource": STORM_SOURCES[city],
        "spots": spots,
        "drainsSource": CITIES[city].drains_source,
        "drainStandard": CITIES[city].design_source,
        "method": "Water model: core/waterdepth.py (screening model). Drains are credited with the city's documented design standard where the road is served; their real present capacity is not published, so no figure for it is given.",
    }
    path = OUTPUTS_DIR / f"findings-{city}.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(spots)} spots from {out['stretches']} stretches ({out['kmFilmed']} km) -> {path}")
    for s in spots:
        z = s["sizing"]
        print(f"  {s['id']} {s['priority']:>6} {s['confidence']:>6} {s['name'][:48]:<48} {s['cause']:<7} {s['depthCm']['2']:>5} cm  needs {z['requiredLs']} L/s  drain {s['drain']['distanceM']} m {s['drain']['class']}  cells {len(s['cells'])}")


if __name__ == "__main__":
    main()
