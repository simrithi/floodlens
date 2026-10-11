"""Run daily by EventBridge Scheduler at 17:00 IST. For every city with a
findings-<city>.json, fetches tomorrow's hourly rain forecast at each spot's
position from Open-Meteo (free, no key), reads the spot's existing depth-vs-rain
curve (analysis.json cell water.curve, already computed by the real pipeline) and
interpolates the expected depth at the forecast intensity. No new model, no
invented conversion factor.

Open-Meteo gives hourly totals; the depth curves are built from 15-minute-burst
design storms. Converting hourly -> 15-minute needs a sourced ratio this project
doesn't have yet, so per the brief: use the hourly value as-is and say so in the
alert, rather than invent a factor.

Writes analysis/alerts/<city>-<date>.json. Sends at most one SNS message per city
per day (guarded by that file already existing -- a re-run is a no-op, not a
second page), only if any spot reaches 5 cm.

Testing: set FORCE_RAIN_MM_HR to skip the real forecast call and use a fixed
value for every spot, so an alert can be produced on demand without waiting for
real rain.
"""

import json
import os
from datetime import datetime, timedelta, timezone

import boto3
import requests

OUTPUTS_BUCKET = os.environ["OUTPUTS_BUCKET"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
SITE_URL = os.environ.get("SITE_URL", "https://d24wvc44c3vaxz.cloudfront.net")
CITIES = ["delhi", "bengaluru"]

WATCH_CM = 5.0
CLOSE_CM = 15.0

s3 = boto3.client("s3")
sns = boto3.client("sns")


def handler(event, context):
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
    results = {}

    for city in CITIES:
        findings = _get_json(f"analysis/findings-{city}.json")
        if findings is None:
            results[city] = {"skipped": "no findings file"}
            continue

        alert_key = f"analysis/alerts/{city}-{tomorrow}.json"
        if _get_json(alert_key) is not None:
            results[city] = {"skipped": "already ran today"}
            continue

        flagged = []
        for spot in findings["spots"]:
            forecast_mm_hr = _forecast_for(spot["lat"], spot["lng"])
            if forecast_mm_hr is None:
                continue
            depth_cm, curve_note = _expected_depth(spot)
            if depth_cm is None:
                continue
            expected = _interp(depth_cm["rainMmHr"], depth_cm["depthCm"], forecast_mm_hr)
            if expected < WATCH_CM:
                continue
            flagged.append(
                {
                    "spotId": spot["id"],
                    "name": spot["name"],
                    "forecastRainMmHr": round(forecast_mm_hr, 1),
                    "expectedDepthCm": round(expected, 1),
                    "action": "consider closing" if expected >= CLOSE_CM else "clear inlets, watch",
                    "note": curve_note,
                }
            )

        alert = {
            "city": city,
            "date": tomorrow,
            "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "spots": flagged,
        }
        s3.put_object(Bucket=OUTPUTS_BUCKET, Key=alert_key, Body=json.dumps(alert), ContentType="application/json")

        if flagged:
            _notify(city, tomorrow, flagged)
        results[city] = {"flagged": len(flagged)}

    return results


def _forecast_for(lat: float, lng: float) -> float | None:
    forced = os.environ.get("FORCE_RAIN_MM_HR")
    if forced is not None:
        return float(forced)
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lng, "hourly": "precipitation", "forecast_days": 2, "timezone": "auto"},
            timeout=20,
        )
        r.raise_for_status()
        hourly = r.json()["hourly"]["precipitation"]
        # Hours 24-47 are tomorrow (today is 0-23).
        return max(hourly[24:48]) if len(hourly) >= 48 else None
    except (requests.RequestException, KeyError, IndexError):
        return None


def _expected_depth(spot: dict) -> tuple[dict | None, str]:
    """The curve of the spot's deepest stretch (across its stretches), plus a note on
    whether the forecast had to be used as hourly-not-burst (always true right now)."""
    best_curve, best_depth = None, -1.0
    for stretch in spot.get("stretches", []):
        analysis = _get_json(f"analysis/{stretch['sequenceId']}-lth/analysis.json")
        if analysis is None:
            continue
        cell = next((c for c in analysis["cells"] if c["id"] == stretch["cellId"]), None)
        if cell is None:
            continue
        if cell["depth2yCm"] > best_depth:
            best_depth, best_curve = cell["depth2yCm"], cell["water"]["curve"]
    note = "hourly rain used as-is; 15-minute burst not modelled (no sourced conversion ratio)"
    return best_curve, note


def _interp(xs: list[float], ys: list[float], x: float) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


def _notify(city: str, date: str, flagged: list[dict]) -> None:
    lines = [f"Tomorrow ({date}), {city.title()}: {len(flagged)} spot(s) expected to hold 5 cm or more of water.", ""]
    for s in flagged:
        lines.append(f"  {s['spotId']} {s['name']}: {s['expectedDepthCm']} cm expected ({s['forecastRainMmHr']} mm/hr forecast) -- {s['action']}")
    lines.append("")
    lines.append(f"{SITE_URL}/map?survey={city}")
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=f"FloodLens: {len(flagged)} spot(s) flagged for tomorrow in {city.title()}",
        Message="\n".join(lines),
    )


def _get_json(key: str) -> dict | None:
    try:
        return json.loads(s3.get_object(Bucket=OUTPUTS_BUCKET, Key=key)["Body"].read())
    except s3.exceptions.NoSuchKey:
        return None
