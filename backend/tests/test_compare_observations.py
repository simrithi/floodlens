import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "compare_observations.py"


def run(tmp_path, observations):
    findings = {"spots": [{"id": "S1", "name": "Somewhere", "depthCm": {"2": 13.0}}]}
    (tmp_path / "findings.json").write_text(json.dumps(findings), encoding="utf-8")
    (tmp_path / "obs.json").write_text(json.dumps({"items": observations}), encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--city", "delhi", "--findings", str(tmp_path / "findings.json"),
         "--observations", str(tmp_path / "obs.json")],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_no_observations(tmp_path):
    assert "No observations recorded yet" in run(tmp_path, [])


def test_hit_rate_and_depth_error(tmp_path):
    obs = [
        {"kind": "observation", "spotId": "S1", "flooded": True, "depthCm": "12"},
        {"kind": "approval", "spotId": "S1", "approved": True},  # not an observation, ignored
        {"kind": "observation", "spotId": "S99", "flooded": False},  # not in findings, skipped
    ]
    out = run(tmp_path, obs)
    assert "hit rate 100% (1/1)" in out
    assert "mean absolute 1.0 cm" in out
    assert "S99: not in findings, skipped" in out
