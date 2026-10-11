"""Road elevation profile from the phone's own sensors: finds sags (underpasses, dips in the road) that the
30 m satellite elevation cannot see.

KartaView's Android app logs a sensor file per sequence (data/kartaview/<seq>/sensors.txt): GPS once a
second (position, speed) and the gravity vector about ten times a second. With the phone fixed in the car,
the gravity vector's tilt in the phone's vertical/forward plane follows the road grade:

    grade = (tilt - mount) - a / g

where mount is the phone's fixed tilt (the median tilt over the drive) and a is the car's forward
acceleration from GPS speed (braking and accelerating also tilt the measured gravity). Grade times
distance, summed, gives the road's elevation along the drive. It drifts over long distances, so only its
short-wavelength part is kept (shorter than ~250 m) and added to the satellite elevation's long-wavelength
part: the satellite gets the hills right, the phone gets the underpasses.

A sag holds water up to the lower of its two rims (a one-dimensional "bathtub", rims searched within
RIM_M either side). Checked on the 45 km Bengaluru ORR drive against OpenStreetMap road tunnels:
satellite elevation alone does not separate them from other road (AUC 0.47); this profile does (AUC 0.69,
median sag 1.6 m at tunnels vs 0.1 m elsewhere). Noisy, so a single sag is a lead to check, not proof.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .elevation import Dem

G = 9.81
STEP_M = 10.0  # profile resolution
HIGHPASS_M = 250.0  # sensor detail kept below this wavelength; satellite elevation above it
RIM_M = 300.0
ROAD_WIDTH_M = 15.0  # water spreads across the carriageway at the bottom of a sag
CATCH_WIDTH_M = 30.0  # road plus footpaths draining into the sag along its ramps


@dataclass
class Profile:
    distance_m: np.ndarray  # along the drive, STEP_M apart
    lat: np.ndarray
    lng: np.ndarray
    time: np.ndarray
    elevation_m: np.ndarray  # satellite long-wave + sensor short-wave
    sag_m: np.ndarray  # depth below the lower rim (0 where water would run off)
    level_m: np.ndarray  # rim level: the height water could rise to at each point
    mount_deg: float
    note: str
    photo_time: dict  # sequence index -> capture time (Unix s)

    def at_time(self, t: float) -> int:
        return int(np.clip(np.searchsorted(self.time, t), 0, len(self.time) - 1))

    def basin(self, i: int) -> tuple[int, int]:
        """Index range of the sag around i (points lying below its rim level)."""
        lvl = self.level_m[i]
        a = b = i
        while a > 0 and self.elevation_m[a - 1] < lvl:
            a -= 1
        while b < len(self.elevation_m) - 1 and self.elevation_m[b + 1] < lvl:
            b += 1
        return a, b

    def ramps(self, i: int, max_m: float = 400.0, bump_m: float = 0.1) -> tuple[int, int]:
        """Index range whose runoff runs down into the sag bottom at i: walk outward while the road keeps
        rising (bumps under bump_m are profile noise), up to max_m each way. Includes ramps above the rim."""
        n, steps = len(self.elevation_m), int(max_m / STEP_M)
        a = i
        while a > 0 and i - a < steps and self.elevation_m[a - 1] >= self.elevation_m[a] - bump_m:
            a -= 1
        b = i
        while b < n - 1 and b - i < steps and self.elevation_m[b + 1] >= self.elevation_m[b] - bump_m:
            b += 1
        return a, b

    def water_depth_m(self, i: int, excess_mm: float) -> float:
        """Standing water at the bottom of the sag around i after excess_mm of runoff (rain beyond drain
        capacity, times runoff coefficient) from its ramps: fill the measured profile from the bottom."""
        if self.sag_m[i] <= 0:
            return 0.0
        a, b = self.basin(i)
        z = self.elevation_m[a : b + 1]
        volume = excess_mm / 1000 * (b - a + 1) * STEP_M * CATCH_WIDTH_M
        def held(level: float) -> float:
            return float(np.clip(level - z, 0, None).sum() * STEP_M * ROAD_WIDTH_M)

        lo, hi = float(z.min()), float(self.level_m[i])
        if volume >= held(hi):
            return hi - lo  # full to the rim; the rest runs on down the road
        bottom = lo
        for _ in range(40):  # bisection on the water level
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if held(mid) < volume else (lo, mid)
        return lo - bottom


def read_sensors(path: Path) -> dict:
    """GPS (t, lat, lng, speed) and gravity (t, x, y, z) rows from a KartaView metadata 2.0 file, plus
    photos: sequence index -> capture time."""
    gps, grav, photos = [], [], {}
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.rstrip().split(":", 2)
            if len(parts) < 3 or parts[1] not in ("g", "x", "f"):
                continue
            try:
                t = float(parts[0])
                v = parts[2].split(";")
                if parts[1] == "f":
                    photos[int(v[1])] = float(v[2]) if v[2] else t
                elif parts[1] == "g":
                    gps.append((t, float(v[0]), float(v[1]), float(v[5]) if len(v) > 5 and v[5] else np.nan))
                else:
                    grav.append((t, float(v[0]), float(v[1]), float(v[2])))
            except (ValueError, IndexError):
                continue
    out = {"gps": np.array(gps), "gravity": np.array(grav)}
    for k, a in out.items():
        if a.size:
            out[k] = a[np.argsort(a[:, 0])]
    out["photos"] = photos
    return out


def build_profile(sensors_path: Path, terrain: Dem) -> Profile | None:
    s = read_sensors(sensors_path)
    gps, grav = s["gps"], s["gravity"]
    if len(gps) < 60 or len(grav) < 600:
        return None  # no gravity log (iPhone uploads use a different format)
    t = gps[:, 0]
    v = np.nan_to_num(gps[:, 3])
    gx, gz = (np.interp(t, grav[:, 0], grav[:, i]) for i in (1, 3))
    tilt = np.degrees(np.arctan2(gz, -gx))
    mount = float(np.median(tilt))
    accel = np.gradient(np.convolve(v, np.ones(3) / 3, mode="same"), t)
    grade = np.radians(tilt - mount) - accel / G
    ds = v * np.gradient(t)
    dist = np.cumsum(ds)
    z_sensor = np.cumsum(ds * np.sin(grade))

    inside = np.array([terrain.contains(la, lo) for la, lo in gps[:, 1:3]])
    if inside.sum() < 30:
        return None
    grid = np.arange(0, dist[-1], STEP_M)
    lat = np.interp(grid, dist, gps[:, 1])
    lng = np.interp(grid, dist, gps[:, 2])
    times = np.interp(grid, dist, t)
    z_dem = np.interp(grid, dist[inside], [terrain.elevation(la, lo) for la, lo in gps[inside, 1:3]])
    zs = np.interp(grid, dist, z_sensor)
    sig = HIGHPASS_M / STEP_M / 2
    elev = gaussian_filter1d(z_dem, sig) + zs - gaussian_filter1d(zs, sig)

    w = int(RIM_M / STEP_M)
    level = np.array([min(elev[max(0, i - w) : i + 1].max(), elev[i : i + w + 1].max()) for i in range(len(elev))])
    return Profile(
        distance_m=grid,
        lat=lat,
        lng=lng,
        time=times,
        elevation_m=elev,
        sag_m=level - elev,
        level_m=level,
        mount_deg=mount,
        photo_time=s["photos"],
        note="phone gravity tilt and GPS speed (short wavelengths) + FABDEM (long wavelengths)",
    )


def frame_index(profile: Profile, sequence_index: int) -> int | None:
    """Profile point where a frame was taken, or None if the sensor log does not list it."""
    t = profile.photo_time.get(sequence_index)
    return None if t is None else profile.at_time(t)
