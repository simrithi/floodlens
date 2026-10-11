"""Sensitivity check: can the pipeline still find a real dip after the curved-surface fix?

Plants a synthetic bowl-shaped depression into the height map of real frames (in the car's lane,
a few metres ahead, on visible road) and runs the same surface fit and dip search as the pipeline.
This tests the geometry, fit and thresholds; it does not simulate depth-model error.

usage: python scripts/test_dip_sensitivity.py [--frames 25]
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ROAD  # noqa: E402
from core.depth import relative_disparity  # noqa: E402
from core.frames import load_frames, load_image, sequence_dir  # noqa: E402
from core.geometry import fit_ground, range_mask, surface_height  # noqa: E402
from core.segment import segment  # noqa: E402
from core.surface import clear_road, find_dips, fit_surface, ground_coords, residual_height  # noqa: E402

DEPTHS_CM = (3, 5, 8, 12)
RADIUS_M = 0.9  # about 2.5 m2
PLACE = [(0.0, 7.0), (0.0, 9.0), (-1.0, 8.0), (1.0, 8.0)]  # (lateral X, forward Z) candidates, metres


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=25)
    parser.add_argument("--size", default="lth")
    args = parser.parse_args()
    _, frames = load_frames(4020141)
    rng = np.random.default_rng(1)
    picked = [frames[i] for i in sorted(rng.choice(len(frames), args.frames, replace=False))]

    results = {d: [] for d in DEPTHS_CM}
    tested = 0
    for f in picked:
        image = load_image(sequence_dir(4020141) / args.size / f.file)
        labels = segment(image)
        disparity = relative_disparity(image)
        ground = fit_ground(disparity, labels == ROAD)
        if ground is None:
            continue
        height = surface_height(disparity, ground)
        X, Z = ground_coords(height.shape, ground)
        trusted = clear_road(labels, image) & range_mask(labels.shape, ground)
        # Place the dip where it is fully on trusted road.
        spot = None
        for x0, z0 in PLACE:
            r2 = (X - x0) ** 2 + (Z - z0) ** 2
            inside = r2 <= RADIUS_M**2
            if inside.sum() > 50 and trusted[inside].mean() > 0.9:
                spot = (x0, z0, r2, inside)
                break
        if spot is None:
            continue
        tested += 1
        x0, z0, r2, inside = spot
        for depth_cm in DEPTHS_CM:
            bowl = np.where(inside, depth_cm / 100 * (1 - r2 / RADIUS_M**2), 0).astype(np.float32)
            h2 = height + bowl
            fit = fit_surface(h2, trusted, ground)
            if fit is None:
                results[depth_cm].append((False, 0.0))
                continue
            dips = find_dips(residual_height(h2, fit, ground), labels, ground, image)
            hit = [d for d in dips if abs(ground.to_ground(*d.centroid)[0] - z0) < 2.0]
            results[depth_cm].append((bool(hit), max((d.depth_cm for d in hit), default=0.0)))

    print(f"frames with a clear patch of lane to test: {tested}/{len(picked)}")
    for depth_cm, rs in results.items():
        found = [r for r in rs if r[0]]
        est = np.median([r[1] for r in found]) if found else float("nan")
        print(f"  planted {depth_cm:>2} cm dip: found in {len(found)}/{len(rs)}  (median measured depth {est:.1f} cm)")


if __name__ == "__main__":
    main()
