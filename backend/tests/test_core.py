"""Unit tests for the numerical core. Every expected value is worked out by hand in the comment beside it,
so a change to the maths shows up here rather than only in the validation numbers."""

import math

import numpy as np
import pytest

from core import geometry, score, validate, waterdepth


# ---- distance and offsets -------------------------------------------------------------------------------

def test_distance_one_degree_of_latitude():
    assert score.distance_m((0.0, 0.0), (1.0, 0.0)) == pytest.approx(111_320, rel=1e-9)


def test_distance_shrinks_east_west_with_latitude():
    # at 60 degrees north a degree of longitude is cos(60) = half as long
    assert score.distance_m((60.0, 0.0), (60.0, 1.0)) == pytest.approx(111_320 * 0.5, rel=1e-6)


def test_distance_is_symmetric_and_zero_for_same_point():
    a, b = (28.61, 77.20), (28.62, 77.21)
    assert score.distance_m(a, b) == pytest.approx(score.distance_m(b, a))
    assert score.distance_m(a, a) == 0.0


def test_offset_forward_heading_north_moves_lat_only():
    lat, lng = geometry.offset_latlng(10.0, 20.0, 0, 111.32, 0)
    assert lat == pytest.approx(10.001, abs=1e-9)
    assert lng == pytest.approx(20.0, abs=1e-9)


def test_offset_forward_heading_east_moves_lng_only():
    lat, lng = geometry.offset_latlng(0.0, 20.0, 90, 111.32, 0)
    assert lat == pytest.approx(0.0, abs=1e-9)
    assert lng == pytest.approx(20.001, abs=1e-9)


def test_offset_right_of_a_north_heading_is_east():
    _, lng = geometry.offset_latlng(0.0, 0.0, 0, 0, 111.32)
    assert lng > 0


def test_offset_round_trip_matches_distance():
    p = (28.6, 77.2)
    q = geometry.offset_latlng(*p, 37, 30.0, 40.0)
    assert score.distance_m(p, q) == pytest.approx(math.hypot(30, 40), rel=1e-3)


# ---- camera ---------------------------------------------------------------------------------------------

def test_intrinsics_follow_the_field_of_view():
    fx, fy, cx, cy = geometry.intrinsics(1920, 1080)
    assert fx == fy
    assert (cx, cy) == (960, 540)
    assert fx == pytest.approx(960 / math.tan(math.radians(geometry.CAMERA.hfov_deg) / 2))


def test_analysis_rows_skip_sky_and_dashboard():
    rows = geometry.analysis_rows(1000)
    assert rows.start == 350  # the upper 35 percent is sky and buildings
    assert rows.stop < 1000   # the car's own bonnet is cut off the bottom


# ---- validation statistics ------------------------------------------------------------------------------

def test_auc_perfect_separation_is_one():
    assert validate.auc(np.array([3.0, 4.0]), np.array([1.0, 2.0])) == 1.0


def test_auc_reversed_is_zero():
    assert validate.auc(np.array([1.0, 2.0]), np.array([3.0, 4.0])) == 0.0


def test_auc_all_ties_is_one_half():
    assert validate.auc(np.array([2.0, 2.0]), np.array([2.0, 2.0])) == 0.5


def test_auc_partial_overlap():
    # pairs: (2>1) (2<3) (4>1) (4>3) -> 3 of 4 won
    assert validate.auc(np.array([2.0, 4.0]), np.array([1.0, 3.0])) == 0.75


def test_bootstrap_ci_is_deterministic_and_ordered():
    pos, neg = np.array([1.0, 2, 3, 4, 5]), np.array([2.0, 3, 4, 5, 6])
    a = validate.bootstrap_ci(pos, neg, validate.auc)
    assert a == validate.bootstrap_ci(pos, neg, validate.auc)
    assert 0.0 <= a[0] <= validate.auc(pos, neg) <= a[1] <= 1.0


def test_bootstrap_ci_collapses_when_groups_are_fully_separated():
    pos, neg = np.array([10.0, 11, 12]), np.array([1.0, 2, 3])
    assert validate.bootstrap_ci(pos, neg, validate.auc) == (1.0, 1.0)


# ---- water balance --------------------------------------------------------------------------------------

FLAT = {"depressionAreaM2": 0.0, "depression": 0.0, "upstream": 1_000.0}
BOWL = {"depressionAreaM2": 400.0, "depression": 0.3, "upstream": 10_000.0}


def test_flow_in_litres_per_second():
    # 0.85 * 50 mm/hr * 1000 m2 / 3600 s
    assert waterdepth.flow_ls(50, 1_000) == pytest.approx(0.85 * 50 * 1000 / 3600)


def test_no_water_when_the_drain_keeps_up_with_the_rain():
    wb = waterdepth.water_balance(FLAT, drain_mm_hr=60)
    assert wb.depth_m(60) == 0.0
    assert wb.depth_m(30) == 0.0


def test_sheet_flow_on_flat_ground():
    # excess 80 mm/hr = 0.08 m/hr; 0.85 * 0.08 * 0.25 h
    wb = waterdepth.water_balance(FLAT, drain_mm_hr=20)
    assert not wb.in_hollow
    assert wb.depth_m(100) == pytest.approx(0.85 * 0.08 * 0.25)


def test_hollow_that_does_not_overflow():
    # volume = 0.85 * 0.02 * 0.25 * 10000 = 42.5 m3; bowl = 0.5 * 400 * 0.3 = 60 m3
    wb = waterdepth.water_balance(BOWL, drain_mm_hr=0)
    assert wb.in_hollow
    assert wb.depth_m(20) == pytest.approx(0.3 * math.sqrt(42.5 / 60))


def test_hollow_that_overflows_spreads_the_excess():
    # volume = 0.85 * 0.05 * 0.25 * 10000 = 106.25 m3; excess over the 60 m3 bowl spreads over max(900, 4 * 400)
    wb = waterdepth.water_balance(BOWL, drain_mm_hr=0)
    assert wb.depth_m(50) == pytest.approx(0.3 + (106.25 - 60) / 1_600)


def test_depth_never_exceeds_the_cap():
    wb = waterdepth.water_balance(BOWL, drain_mm_hr=0)
    assert wb.depth_m(100_000) == waterdepth.MAX_DEPTH_M


def test_depth_never_falls_as_rain_increases():
    wb = waterdepth.water_balance(BOWL, drain_mm_hr=10)
    depths = [wb.depth_m(r) for r in range(0, 200, 10)]
    assert depths == sorted(depths)


def test_a_bigger_drain_never_makes_it_worse():
    wb = waterdepth.water_balance(BOWL, drain_mm_hr=0)
    assert wb.depth_m(80, drain_mm_hr=40) <= wb.depth_m(80, drain_mm_hr=0)


def test_dashcam_dips_make_a_hollow_where_the_terrain_has_none():
    wb = waterdepth.water_balance(FLAT, drain_mm_hr=0, dip_area_m2=50.0, dip_depth_m=0.08)
    assert wb.in_hollow
    assert wb.hollow_depth_m == 0.08
    assert wb.pool_m2 == 50.0
