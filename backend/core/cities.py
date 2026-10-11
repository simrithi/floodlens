"""Cities the pipeline can analyse: the area covered by the terrain and drainage layers, and where they live.

Every city-wide layer (elevation tiles, hydrology rasters, OSM drains, rain history, design storms) is
loaded per city. A dashcam sequence belongs to the city whose bounds contain its frames.
Delhi keeps the file names it had before other cities were added, so existing data stays valid.
"""

from dataclasses import dataclass
from pathlib import Path

from .config import GEO_DIR

FABDEM_BASE = "https://data.bris.ac.uk/datasets/25wfy0f9ukoge2gs7a5mqpq2j7"


@dataclass(frozen=True)
class City:
    key: str
    name: str
    bounds: tuple[float, float, float, float]  # west, south, east, north (hydrology + OSM area)
    lat: int  # 1-degree tile corner (south-west), e.g. 28 for N28
    lng: int
    rain_point: tuple[float, float]
    geo_dir: Path
    waterways_cache: str = "osm_waterways.json"
    drains_file: str = ""  # in data/outputs; default drains-<key>.geojson
    # Drain design standard (rain intensity the storm drains are built to take) and where it comes from.
    design_mm_hr: float = 25.0
    design_source: str = ""
    # Official drain network (lines with a tier) in geo_dir, or "" to use OpenStreetMap waterways.
    official_drains: str = ""
    drains_source: str = "OpenStreetMap waterways (drains, canals, rivers)"
    served_m: float = 30.0  # a road is served by the network if an official drain is this close

    @property
    def center(self) -> tuple[float, float]:
        w, s, e, n = self.bounds
        return (s + n) / 2, (w + e) / 2

    @property
    def dem_tile(self) -> str:
        return f"Copernicus_DSM_COG_10_N{self.lat:02d}_00_E{self.lng:03d}_00_DEM"

    @property
    def dem_url(self) -> str:
        return f"https://copernicus-dem-30m.s3.amazonaws.com/{self.dem_tile}/{self.dem_tile}.tif"

    @property
    def fabdem_tile(self) -> str:
        return f"N{self.lat:02d}E{self.lng:03d}_FABDEM_V1-0"

    @property
    def fabdem_zip_url(self) -> str:
        # FABDEM is published as 10x10 degree zips named after their corners.
        s, w = self.lat // 10 * 10, self.lng // 10 * 10
        return f"{FABDEM_BASE}/N{s:02d}E{w:03d}-N{s + 10:02d}E{w + 10:03d}_FABDEM_V1-0.zip"

    @property
    def fabdem_path(self) -> Path:
        return self.geo_dir / f"{self.fabdem_tile}.tif"

    @property
    def hydro_dir(self) -> Path:
        return self.geo_dir / "hydro"

    @property
    def drains_name(self) -> str:
        return self.drains_file or f"drains-{self.key}.geojson"

    def contains(self, lat: float, lng: float) -> bool:
        w, s, e, n = self.bounds
        return s <= lat <= n and w <= lng <= e


CITIES = {
    "delhi": City(
        key="delhi",
        name="Delhi",
        bounds=(77.00, 28.40, 77.40, 28.90),
        lat=28,
        lng=77,
        rain_point=(28.6315, 77.2167),
        geo_dir=GEO_DIR,
        waterways_cache="osm_waterways_delhi.json",
        drains_file="drains.geojson",
        design_mm_hr=25.0,
        design_source="Existing Delhi storm drains were designed for about 25 mm/hr (1976 drainage plan, cited in the IIT Delhi Drainage Master Plan 2018)",
    ),
    "bengaluru": City(
        key="bengaluru",
        name="Bengaluru",
        bounds=(77.45, 12.80, 77.85, 13.00),  # FABDEM tile N12E077 ends at 13.0 N
        lat=12,
        lng=77,
        rain_point=(12.9500, 77.6680),  # HAL airport, near the ORR survey
        geo_dir=GEO_DIR / "bengaluru",
        # BBMP Master Plan for Remodelling of Storm Water Drains (2010, STUP Consultants), sec. 4.2.3.2 and
        # Table 4.5: drains sized for the 2-year storm; 56.2 mm/hr at a 30-minute time of concentration.
        design_mm_hr=56.2,
        design_source="BBMP Storm Water Drain Master Plan 2010, Table 4.5: drains sized for the 2-year storm, 56.2 mm/hr at 30 minutes",
        official_drains="swd_ksrsac_2022.json",
        drains_source="Official storm-water drain network, KSRSAC 2022 (BBMP), via OpenCity (public domain)",
    ),
}


def city(key: str) -> City:
    return CITIES[key]


def city_for(lat: float, lng: float) -> City:
    for c in CITIES.values():
        if c.contains(lat, lng):
            return c
    raise ValueError(f"no city covers ({lat}, {lng}); add one to core/cities.py")
