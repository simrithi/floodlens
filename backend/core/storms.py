"""Design storms (15-minute rainfall intensity for 2/5/10-year return periods) per city.

Delhi, from the IIT Delhi Drainage Master Plan (2018). Source: "Drainage Master Plan for NCT of Delhi, Final Report", IIT Delhi, July 2018, section 4.4
(Tables 4.4-1 and 4.4-2): annual maximum 15-minute rainfall at the only two Delhi stations with
long sub-hourly records, fitted with a Gumbel (EV1) distribution by probability-weighted moments.
https://ifc.delhi.gov.in/sites/default/files/inline-files/main_report_dmp_version51.pdf

The same report gives the existing storm drains' design capacity context: the 1976 system was built
for about 25 mm/hr (Haskoning summary of the new master plan, which targets 70 mm/hr).

Bengaluru: no published sub-hourly annual maxima were found. Satya Priya, "A study on intensity of rainfall
in urban Bangalore areas", IRJET 4(6), 2017, Table 1 gives the mean and standard deviation of the annual
maximum 24-hour rainfall at 17 IMD stations (1972-2011). We fit a Gumbel distribution to those by the
method of moments and reduce 24 h to 15 minutes with the IMD empirical rule P_t = P_24 (t/24)^(1/3),
as the paper itself does. This is a weaker basis than Delhi's measured 15-minute record: the 1/3 rule is
a regional average, not a measurement.
https://www.irjet.net/archives/V4/i6/IRJET-V4I6272.pdf
"""

import math
from dataclasses import dataclass
from functools import lru_cache

# Annual maximum 15-minute rainfall depth (mm), as printed in the report (missing years omitted).
SAFDARJUNG_15MIN_MM = [
    21.5, 16.5, 13.5, 21, 10.6, 27, 18.8, 21.5, 18.5, 20.2, 22, 35.8, 20.7, 22, 18.5, 41, 19, 18, 34, 30, 18, 20, 27, 29, 30,
]  # 1979-2008
PALAM_15MIN_MM = [
    20, 23.5, 13.5, 18, 14, 15, 14, 20, 24, 20.5, 18, 22, 19, 24.5, 22, 20, 24, 20, 24.5, 26, 20.4, 30, 16, 16.4, 22, 20, 30,
]  # 1977-2008

DRAIN_DESIGN_MM_HR = 25.0  # existing Delhi storm drains (1976 plan)
DRAIN_TARGET_MM_HR = 70.0  # new Drainage Master Plan target


@dataclass(frozen=True)
class Station:
    name: str
    lat: float
    lng: float
    mu: float  # Gumbel location, mm/hr (15-minute intensity)
    alpha: float  # Gumbel scale, mm/hr

    def intensity(self, return_period_years: float) -> float:
        """15-minute rainfall intensity (mm/hr) exceeded on average once every T years."""
        y = -math.log(-math.log(1 - 1 / return_period_years))
        return self.mu + self.alpha * y


def gumbel_pwm(depths_mm: list[float], minutes: int = 15) -> tuple[float, float]:
    """Gumbel parameters by probability-weighted moments, exactly as in the report (section 4.4)."""
    x = sorted(d * 60 / minutes for d in depths_mm)  # intensities, ascending
    n = len(x)
    b0 = sum(x) / n
    b1 = sum((j - 1) * x[j - 1] for j in range(2, n + 1)) / (n * (n - 1))
    alpha = (2 * b1 - b0) / math.log(2)
    mu = b0 - 0.5772 * alpha
    return mu, alpha


# Bengaluru: annual maximum 24-hour rainfall, mean and standard deviation (mm), IRJET 2017 Table 1.
# Station positions are approximate (town or campus centre); the paper gives none.
BENGALURU_24H_MM = {
    "Bangalore Airport (HAL)": (12.9500, 77.6680, 82.02, 24.25),
    "Krishnarajapura": (13.0050, 77.6950, 66.59, 47.04),
    "Sarjapur": (12.8600, 77.7860, 67.81, 25.62),
    "Bangalore City": (12.9720, 77.5940, 89.02, 31.53),
}
IMD_REDUCTION_15MIN = (0.25 / 24) ** (1 / 3)  # P_15min / P_24h


def gumbel_moments_24h_to_15min(mean_mm: float, std_mm: float) -> tuple[float, float]:
    """Gumbel parameters (mm/hr, 15-minute intensity) from 24 h annual-maximum mean and standard deviation."""
    alpha = std_mm * math.sqrt(6) / math.pi
    mu = mean_mm - 0.5772 * alpha
    to_intensity = IMD_REDUCTION_15MIN * 60 / 15  # 24 h depth -> 15-min depth -> mm/hr
    return mu * to_intensity, alpha * to_intensity


STORM_SOURCES = {
    "delhi": "IIT Delhi Drainage Master Plan 2018, sec. 4.4 (Gumbel fit of annual max 15-min rainfall)",
    "bengaluru": "BBMP Storm Water Drain Master Plan 2010 (STUP Consultants), Table 4.5: IDF from IMD Bangalore 15-minute rainfall 1976-2000",
}


@dataclass(frozen=True)
class TableStation:
    """A published intensity table instead of a fitted distribution."""

    name: str
    lat: float
    lng: float
    table: tuple[tuple[float, float], ...]  # (return period years, 15-minute intensity mm/hr)

    def intensity(self, return_period_years: float) -> float:
        ts = [t for t, _ in self.table]
        vs = [v for _, v in self.table]
        x = math.log(return_period_years)
        xs = [math.log(t) for t in ts]
        if x <= xs[0]:
            return vs[0]
        for (x0, v0), (x1, v1) in zip(zip(xs, vs), zip(xs[1:], vs[1:])):
            if x <= x1:
                return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
        return vs[-1]


# BBMP Master Plan for Remodelling of Storm Water Drains (2010), Table 4.5: power-law IDF from IMD Bangalore
# 15-minute rainfall 1976-2000, at 15 minutes duration.
BBMP_2010_15MIN = ((2, 67.4), (5, 85.0), (10, 87.3))


@lru_cache(maxsize=2)
def stations(city_key: str = "delhi") -> tuple:
    if city_key == "bengaluru":
        return (TableStation("IMD Bangalore (BBMP 2010 IDF)", 12.9720, 77.5940, BBMP_2010_15MIN),)
    s = gumbel_pwm(SAFDARJUNG_15MIN_MM)
    p = gumbel_pwm(PALAM_15MIN_MM)
    return (
        Station("Safdarjung", 28.5845, 77.2052, *s),
        Station("Palam", 28.5665, 77.1031, *p),
    )


def nearest_station(lat: float, lng: float, city_key: str = "delhi"):
    def d2(s) -> float:
        return (s.lat - lat) ** 2 + ((s.lng - lng) * math.cos(math.radians(lat))) ** 2

    return min(stations(city_key), key=d2)


RETURN_PERIODS = (2, 5, 10)
