"""Run the FloodLens pipeline on downloaded dashcam frames.

examples:
  python run_local.py                         # all 207 frames, 1280x720 copies
  python run_local.py --size full             # 4K originals (analysed at 1920x1080)
  python run_local.py --segments minto --limit 10
"""

import argparse
import json
from pathlib import Path

from core.pipeline import rescore, run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sequence", type=int, default=4020141, help="KartaView sequence id")
    parser.add_argument("--size", choices=["lth", "full"], default="lth", help="which downloaded copy to analyse")
    parser.add_argument("--segments", help="comma-separated segment names, e.g. ito,minto")
    parser.add_argument("--limit", type=int, help="analyse only the first N frames")
    parser.add_argument("--confidence", type=float, default=0.35, help="minimum pothole detection confidence")
    parser.add_argument("--max-width", type=int, default=1920, help="downscale frames wider than this")
    parser.add_argument("--out", type=Path, help="output folder (default data/outputs/<sequence>-<size>)")
    parser.add_argument("--rescore", action="store_true", help="recompute risk from an existing analysis.json (no neural networks)")
    args = parser.parse_args()

    if args.rescore:
        analysis = rescore(args.sequence, args.size, args.out)
    else:
        analysis = run(
            sequence_id=args.sequence,
            size=args.size,
            segments=args.segments.split(",") if args.segments else None,
            limit=args.limit,
            out_dir=args.out,
            pothole_confidence=args.confidence,
            max_width=args.max_width,
        )
    print(json.dumps(analysis["summary"], indent=2))
    for c in sorted(analysis["cells"], key=lambda c: -c["risk"])[:5]:
        print(
            f"{c['id']:>9}  risk {c['risk']:>3}  2-yr water {c['depth2yCm']:>5} cm  dip {c['maxDipCm']:>5} cm  "
            f"hollow {c['hollowDepthCm']} cm  drain {c['drain']['distanceM']} m  potholes {c['potholes']}"
        )


if __name__ == "__main__":
    main()
