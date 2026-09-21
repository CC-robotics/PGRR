# Swept-capsule failure-location summary

## Boundary

exact runtime failure categories and original-scan distances rounded to 0.001 m; two train-only anchors. This does not authorize a threshold change.

## Results

- Trace decisions: 89
- Empty scan outputs: 55
- Failed action instances by category: `{"segment_endpoint": 1278, "segment_interior": 557}`
- Failed action instances inside empty decisions: `{"segment_endpoint": 700, "segment_interior": 455}`
- Decisions containing each category: `{"segment_endpoint": 89, "segment_interior": 89}`
- Minimum segment clearance by category: `{"segment_endpoint": {"maximum_m": 0.895, "median_m": 0.4175, "minimum_m": 0.017}, "segment_interior": {"maximum_m": 0.822, "median_m": 0.01, "minimum_m": 0.003}}`
- Clearance deficit by category: `{"segment_endpoint": {"maximum_m": 0.883, "median_m": 0.418, "minimum_m": 0.0050000000000000044}, "segment_interior": {"maximum_m": 0.893, "median_m": 0.475, "minimum_m": 0.07800000000000007}}`
- Selected actions: `{"21": 20, "22": 69}`
- Selected actions when scan retained a temporary candidate: `{"22": 34}`
- Temporary actions selected when scan was nonempty: 0
- Scan nonempty but final temporary mask empty: 34
- Scan and final temporary masks both nonempty: 0
- Temporary selections when final temporary mask was nonempty: 0

The next design step must distinguish trajectory-shape limitations from clearance
selection. Endpoint/interior failures cannot be treated as harmless initial overlap.
