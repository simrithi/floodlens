"""Compare officers' ground reports with what FloodLens predicted, so the project gains real validation over time.

Officers record "it flooded / it did not, about N cm" per spot through the actions API (DynamoDB). This reads
those observations and the city's findings and reports:

  hit rate      of the spots reported flooded, how many FloodLens had flagged (every spot in findings is flagged)
  false alarms  spots reported not flooded
  depth error   for reports with a depth: reported cm against the 2-year-storm depth predicted for that spot

Caveat printed with the result: a report describes one day's rain, the prediction is for a 2-year design storm, so
depth error is only meaningful on a day with heavy rain. Spots nobody has reported on are not counted either way.

usage:
  python scripts/compare_observations.py --city bengaluru --api https://<actions Function URL>
  python scripts/compare_observations.py --city delhi --observations observations.json   (a saved GET response)
"""

import argparse
import json
import urllib.request
from pathlib import Path
from statistics import mean

OUTPUTS = Path(__file__).resolve().parent.parent.parent / "data" / "outputs"


def load_observations(args) -> list[dict]:
    if args.observations:
        data = json.loads(Path(args.observations).read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(f"{args.api}?city={args.city}", timeout=20) as r:
            data = json.load(r)
    items = data["items"] if isinstance(data, dict) else data
    return [i for i in items if i.get("kind") == "observation"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--city", required=True)
    p.add_argument("--api", help="actions Function URL (GET ?city=...)")
    p.add_argument("--observations", help="a saved response instead of calling the API")
    p.add_argument("--findings", type=Path, help="findings JSON (default data/outputs/findings-<city>.json)")
    args = p.parse_args()
    if not args.api and not args.observations:
        p.error("give --api or --observations")

    findings = json.loads((args.findings or OUTPUTS / f"findings-{args.city}.json").read_text(encoding="utf-8"))
    spots = {s["id"]: s for s in findings["spots"]}
    obs = load_observations(args)
    if not obs:
        print("No observations recorded yet.")
        return

    hits = misses = 0
    errors: list[float] = []
    for o in obs:
        spot = spots.get(o["spotId"])
        if spot is None:
            print(f"  {o['spotId']}: not in findings, skipped")
            continue
        flooded = bool(o["flooded"])
        hits += flooded
        misses += not flooded
        depth = o.get("depthCm")
        if flooded and depth not in (None, ""):
            predicted = spot["depthCm"]["2"]
            errors.append(float(depth) - predicted)
            print(f"  {o['spotId']} {spot['name']}: reported {float(depth):.0f} cm, predicted {predicted:.0f} cm (2-year storm)")
        else:
            print(f"  {o['spotId']} {spot['name']}: reported {'flooded' if flooded else 'not flooded'}")

    total = hits + misses
    print(f"\n{total} observations on flagged spots: {hits} flooded, {misses} not flooded")
    print(f"hit rate {hits / total:.0%} ({hits}/{total}); false alarms {misses}")
    if errors:
        print(f"depth error over {len(errors)} reports: mean {mean(errors):+.1f} cm, mean absolute {mean(abs(e) for e in errors):.1f} cm")
    print("Caveat: one day's rain against a 2-year design storm; small samples say little.")


if __name__ == "__main__":
    main()
