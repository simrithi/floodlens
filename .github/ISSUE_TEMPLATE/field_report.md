---
name: Field report
about: A spot flooded, or did not, and you want it recorded against the prediction
labels: validation
---

**City and spot** (for example Bengaluru, S3 Outer Ring Road, Panathur; spot ids change when findings are rebuilt, so please also give the road name)

**Date and rain**

**Did it flood?** yes / no, and roughly how deep (cm)

**Source** (your own observation, a news report, a municipal record; a link if there is one)

Reports are used to check predictions with `backend/scripts/compare_observations.py`. A missing report is not evidence that a road did not flood.
