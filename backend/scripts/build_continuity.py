"""Frame continuity: align consecutive frames, check kerb lines agree, and join them into continuous lines.

Writes data/outputs/<sequence>-<size>/continuity.json (trajectory, per-pair agreement, statistics) and
kerb_lines.geojson (continuous kerb lines for the map).

usage: python scripts/build_continuity.py [--size lth]
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import OUTPUTS_DIR  # noqa: E402
from core.continuity import fuse_trajectory, lateral_gap, place, relative_pose, to_latlng, to_local  # noqa: E402
from core.frames import load_image, sequence_dir  # noqa: E402

SEQ = 4020141
JOIN_M = 0.75  # consecutive kerb pieces closer than this (sideways, where they overlap) are the same kerb
BIN_M = 1.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", default="lth")
    args = parser.parse_args()
    out_dir = OUTPUTS_DIR / f"{SEQ}-{args.size}"
    analysis = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    frames = sorted(analysis["frames"], key=lambda f: f["index"])
    lat0, lng0 = frames[0]["lat"], frames[0]["lng"]

    report = {"segments": {}, "pairs": []}
    features = []
    all_gaps = {"gps": [], "fused": []}

    segments = sorted({f["segment"] for f in frames})
    # 1. Visual odometry for consecutive frames (always on the 1280p copy: fast, enough features).
    poses = {}
    for seg in segments:
        fs = [f for f in frames if f["segment"] == seg]
        for a, b in tqdm(list(zip(fs, fs[1:])), desc=f"odometry {seg}", unit="pair"):
            if b["index"] != a["index"] + 1:
                continue
            img = lambda f: load_image(sequence_dir(SEQ) / "lth" / f["image"].split("/")[-1])  # noqa: E731
            poses[a["index"]] = relative_pose(img(a), img(b))

    ok = [p for p in poses.values() if p.ok]
    mount_yaw = float(np.median([math.degrees(math.atan2(p.direction[0], p.direction[1])) for p in ok]))
    report["visualOdometry"] = {
        "pairs": len(poses),
        "ok": len(ok),
        "mountYawDeg": round(mount_yaw, 2),
        "note": "Car travels mountYawDeg to the right of where the camera points (phone mounted slightly turned).",
    }

    for seg in segments:
        fs = [f for f in frames if f["segment"] == seg]
        gps_en = np.array([to_local(f["lat"], f["lng"], lat0, lng0) for f in fs])
        gps_heading = np.array([f["heading"] for f in fs], dtype=float)
        seg_poses = [poses.get(fs[i]["index"]) if fs[i + 1]["index"] == fs[i]["index"] + 1 else None for i in range(len(fs) - 1)]
        xy, heading = fuse_trajectory(gps_en, gps_heading, seg_poses, mount_yaw)

        # 2. Place every kerb with both trajectories; camera heading = travel heading - mount yaw.
        placed = {"gps": [], "fused": []}
        for i, f in enumerate(fs):
            for mode, en, hd in (("gps", gps_en[i], gps_heading[i]), ("fused", xy[i], heading[i])):
                placed[mode].append(
                    {k["side"]: place(np.array(k["ground"]), en, hd - mount_yaw) for k in f.get("kerbs", []) if len(k["ground"]) >= 3}
                )

        # 3. Agreement between consecutive frames, same side, where they overlap.
        seg_gaps = {"gps": [], "fused": []}
        for i in range(len(fs) - 1):
            if fs[i + 1]["index"] != fs[i]["index"] + 1:
                continue
            for side in ("left", "right"):
                row = {"from": fs[i]["index"], "to": fs[i + 1]["index"], "side": side}
                for mode in ("gps", "fused"):
                    a, b = placed[mode][i].get(side), placed[mode][i + 1].get(side)
                    hd = heading[i] if mode == "fused" else gps_heading[i]
                    gap = lateral_gap(a, b, hd) if a is not None and b is not None else None
                    row[mode] = None if gap is None else round(gap, 2)
                    if gap is not None:
                        seg_gaps[mode].append(gap)
                        all_gaps[mode].append(gap)
                if row["gps"] is not None or row["fused"] is not None:
                    report["pairs"].append(row)

        # 4. Chain agreeing pieces into continuous lines (fused trajectory), resample along the road.
        for side in ("left", "right"):
            chain: list[int] = []

            def flush(chain: list[int]) -> None:
                if len(chain) < 2:
                    return
                pts = np.vstack([placed["fused"][j][side] for j in chain])
                t = math.radians(float(np.mean(heading[chain[0] : chain[-1] + 1])))
                fwd = np.array([math.sin(t), math.cos(t)])
                rgt = np.array([math.cos(t), -math.sin(t)])
                s, x = pts @ fwd, pts @ rgt
                bins = np.arange(s.min(), s.max() + BIN_M, BIN_M)
                line = []
                for lo in bins:
                    m = (s >= lo) & (s < lo + BIN_M)
                    if m.sum():
                        en = fwd * (lo + BIN_M / 2) + rgt * float(np.median(x[m]))
                        lat, lng = to_latlng(en[0], en[1], lat0, lng0)
                        line.append([round(lng, 7), round(lat, 7)])
                if len(line) >= 4:
                    beyond = [k["beyond"] for j in chain for k in fs[j].get("kerbs", []) if k["side"] == side]
                    features.append(
                        {
                            "type": "Feature",
                            "properties": {
                                "segment": seg,
                                "side": side,
                                "frames": [fs[j]["index"] for j in chain],
                                "lengthM": round(float(s.max() - s.min()), 1),
                                "beyond": max(set(beyond), key=beyond.count) if beyond else "edge",
                            },
                            "geometry": {"type": "LineString", "coordinates": line},
                        }
                    )

            for i in range(len(fs)):
                has = side in placed["fused"][i]
                if not has:
                    flush(chain)
                    chain = []
                    continue
                if chain and fs[i]["index"] == fs[chain[-1]]["index"] + 1:
                    gap = lateral_gap(placed["fused"][chain[-1]][side], placed["fused"][i][side], heading[i])
                    if gap is not None and gap > JOIN_M:
                        flush(chain)
                        chain = []
                elif chain:
                    flush(chain)
                    chain = []
                chain.append(i)
            flush(chain)

        report["segments"][seg] = {
            "frames": len(fs),
            "trajectory": [
                {"index": f["index"], "lat": round(to_latlng(*xy[i], lat0, lng0)[0], 7), "lng": round(to_latlng(*xy[i], lat0, lng0)[1], 7), "heading": round(float(heading[i]) % 360, 2)}
                for i, f in enumerate(fs)
            ],
            "gpsVsFusedShiftM": round(float(np.median(np.linalg.norm(xy - gps_en, axis=1))), 2),
            **{f"{mode}MedianGapM": round(float(np.median(g)), 2) if g else None for mode, g in seg_gaps.items()},
        }

    def stats(g: list[float]) -> dict:
        g = np.array(g)
        return {"pairs": int(g.size), "medianGapM": round(float(np.median(g)), 2), "within75cm": round(float((g <= JOIN_M).mean()), 3)}

    report["agreement"] = {mode: stats(g) for mode, g in all_gaps.items() if g}
    report["kerbLines"] = {"count": len(features), "totalLengthM": round(sum(f["properties"]["lengthM"] for f in features), 1)}
    (out_dir / "continuity.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out_dir / "kerb_lines.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")

    print(json.dumps({k: report[k] for k in ("visualOdometry", "agreement", "kerbLines")}, indent=2))
    for seg, s in report["segments"].items():
        print(seg, {k: v for k, v in s.items() if k != "trajectory"})


if __name__ == "__main__":
    main()
