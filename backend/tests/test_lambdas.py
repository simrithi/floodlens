import json

import pytest

from conftest import load_handler


# ---- officer-brief: the checks that stop an unverified brief reaching the UI -------------------------------

@pytest.fixture
def brief(s3):
    mod = load_handler("officer-brief")
    mod.s3 = s3
    return mod


def test_numbers_match_across_scripts_and_formats(brief):
    # Latin and Devanagari digits, thousands separators and a trailing full stop all normalise.
    assert brief._numbers_in("978 और १,५३७ और १३.") == {"978", "1537", "13"}


def test_kannada_is_not_offered(brief):
    assert set(brief.LANGUAGE_NAMES) == {"en", "hi"}
    assert set(brief.MODELS) == {"en", "hi"}


def test_a_number_not_in_the_findings_is_detected(brief):
    findings = brief._numbers_in('{"depthCm": 13, "requiredLs": 978}')
    assert brief._numbers_in("needs 999 L/s") - findings == {"999"}


def test_brief_input_drops_methods_text_and_keeps_spots(brief):
    findings = {
        "cityName": "Delhi",
        "flagCm": 5,
        "method": "core/waterdepth.py internal note",
        "spots": [{"id": "S1", "name": "Somewhere", "why": "w", "lat": 1.0, "internal": "x"}],
    }
    shown = brief._brief_input(findings)
    assert "method" not in json.dumps(shown)
    assert shown["spots"] == [{"id": "S1", "name": "Somewhere", "why": "w"}]


def test_brief_rate_limit_allows_the_quota_then_blocks(brief):
    results = [brief._check_rate_limit() for _ in range(brief.RATE_LIMIT_PER_HOUR + 2)]
    assert results.count(True) == brief.RATE_LIMIT_PER_HOUR
    assert results[-1] is False


# ---- frame-check ------------------------------------------------------------------------------------------

@pytest.fixture
def check(s3):
    mod = load_handler("frame-check")
    mod.s3 = s3
    return mod


def test_frame_check_rate_limit(check):
    results = [check._check_rate_limit() for _ in range(32)]
    assert results.index(False) == 30  # the 31st call is the first refused


def test_frame_check_collects_best_frame_first_from_the_real_layout(check, s3):
    analysis = {
        "frames": [{"index": i, "image": f"frames/{i:04d}.jpg"} for i in (10, 11, 12, 13, 14)],
        "cells": [{"id": "c1", "frameIndexes": [11, 12, 13, 14]}, {"id": "other", "frameIndexes": [10]}],
    }
    s3.put_object(Bucket="outputs-test", Key="4020141-lth/analysis.json", Body=json.dumps(analysis))
    spot = {"sequence": 4020141, "cells": ["c1"], "frame": {"index": 12, "image": "4020141-lth/frames/0012.jpg"}}
    frames = check._collect_frames(spot)
    assert frames[0] == {"index": 12, "key": "4020141-lth/frames/0012.jpg"}
    assert len(frames) == 4
    assert [f["index"] for f in frames].count(12) == 1  # the best frame is not repeated
    assert all(f["index"] != 10 for f in frames)  # a cell that is not the spot's is ignored


def test_missing_cache_key_is_none_not_an_error(check):
    assert check._get_json("analysis/checks/nowhere/S1.json") is None


# ---- invoke-frame: results go to S3 so Step Functions' 256 KB state limit is never reached -------------------

def test_invoke_frame_returns_a_pointer_and_stores_the_record(s3):
    mod = load_handler("invoke-frame")
    mod.s3 = s3
    record = {"index": 5, "ground": None, "potholes": []}

    class Body:
        def read(self):
            return json.dumps(record).encode()

    mod.sm = type("SM", (), {"invoke_endpoint": staticmethod(lambda **kw: {"Body": Body()})})()
    event = {
        "frame": {"file": "0005.jpg"}, "rawBucket": "raw", "rawPrefix": "kartaview/1/lth",
        "outputBucket": "out", "outputPrefix": "1-lth",
    }
    result = mod.handler(event, None)
    assert result == {"s3Key": "1-lth/frame-records/0005.jpg.json"}
    assert json.loads(s3.store[("out", result["s3Key"])]) == record
    assert len(json.dumps(result)) < 100  # 422 of these fit easily in one state


# ---- forecast ---------------------------------------------------------------------------------------------

def test_forecast_interpolates_the_depth_curve():
    fc = load_handler("forecast")
    rain, depth = [0, 50, 100], [0.0, 8.0, 14.0]
    assert fc._interp(rain, depth, 75) == pytest.approx(11.0)
    assert fc._interp(rain, depth, 150) == 14.0  # clamped to the curve's end, not extrapolated
    assert fc._interp(rain, depth, -5) == 0.0


# ---- the public endpoints reject odd input before touching S3 ------------------------------------------------

@pytest.mark.parametrize("body", [
    {"city": "../../x", "spotId": "S1"},
    {"city": "delhi", "spotId": "../S1"},
    {"city": "delhi", "spotId": "S1/../../x"},
    {"city": "Delhi", "spotId": "S1"},
    {"city": 7, "spotId": "S1"},
    {"city": "delhi", "spotId": ["S1"]},
])
def test_frame_check_rejects_bad_city_or_spot(check, body):
    result = check.handler({"body": json.dumps(body)}, None)
    assert result["statusCode"] == 400


@pytest.mark.parametrize("body", [
    {"city": "../../x", "language": "en"},
    {"city": "Delhi", "language": "en"},
    {"city": 7, "language": "en"},
    {"city": "delhi", "language": "kn"},
    {"city": "delhi", "language": "fr"},
])
def test_brief_rejects_bad_city_or_language(brief, body):
    result = brief.handler({"body": json.dumps(body)}, None)
    assert result["statusCode"] == 400
