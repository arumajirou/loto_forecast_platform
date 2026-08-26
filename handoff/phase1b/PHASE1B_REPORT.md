# Canonical Inventory Phase 1B

- source SHA: `8af95b2be18280589cbbb13aa1fc32dfb793767c`
- recovered Expanded v2: 244
- all execution surfaces: 55
- repaired canonical observations: 554
- repaired identity candidates: 306
- alias groups requiring review: 2
- source typo detected: True

## Source defect

`expanded_inventory_counts()` references `AUTOGLUON_BROAD_V1_ID`, while the module defines `AUTOGLOUON_BROAD_V1_ID`.

Expanded implementations were recovered without modifying the source tree.
