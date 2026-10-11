"""Validate FloodLens against publicly reported Delhi waterlogging hotspots.

Writes data/outputs/validation.json (read by the UI) and prints a summary.

usage: python run_validate.py
"""

from core.validate import run


def main() -> None:
    v = run()
    t = v["terrain"]
    print(f"Reference hotspots: {v['reference']['count']}")
    print(
        f"A. Terrain: {t['hitRate']:.0%} of hotspots on low ground (<= {t['lowGroundThresholdM']} m vs 400 m around) "
        f"vs {t["controlRate"]:.0%} of {t["controls"]} random main-road points; lift {t["lift"]}x, AUC {t["auc"]} (95% CI {t["aucCi95"][0]}-{t["aucCi95"][1]}), hotspot rate CI {t["hitRateCi95"]}"
    )
    print(f"   median height vs surroundings: hotspots {t['medianRelativeHotspotsM']} m, controls {t['medianRelativeControlsM']} m")
    s = v["terrainSurface"]
    print(f"   (surface model instead of bare earth: AUC {s['auc']}, lift {s['lift']}x)")
    hy = v["hydrology"]
    for k, f in hy["features"].items():
        print(f"   water flow, {f['label']} within {hy['radiusM']} m: AUC {f['auc']} (95% CI {f['aucCi95'][0]}-{f['aucCi95'][1]})")
    for size, c in v["cells"].items():
        if not c:
            print(f"B. {size}: no analysis.json")
            continue
        print(
            f"B. {size}: {c['cellsNearHotspot']}/{c['cells']} cells within {c['nearRadiusM']} m of {len(c['hotspotsCovered'])} hotspots "
            f"({', '.join(h['name'] for h in c['hotspotsCovered'])}); mean risk near {c['meanRiskNear']} vs other {c['meanRiskOther']}; "
            f"top-5 precision {c['precisionTop5']}; AUC {c['auc']}"
        )


if __name__ == "__main__":
    main()
