# PGRR extension v1: scenario variables

> Draft design material only. This table contains no simulator or evaluation results.

| Family | Interaction question | Variable | Candidate values |
|---|---|---|---|
| diagonal_cut_in_corridor | diagonal pedestrian cut-in ahead of the robot in a shelf corridor | cut_side | left, right |
|  |  | cut_angle_deg | 35, 55 |
|  |  | longitudinal_phase | early, nominal, late |
|  |  | speed_ratio_to_robot_nominal | 0.7, 1.0 |
|  |  | lateral_offset_m | 0.25, 0.45 |
| occluded_side_emergence | pedestrian emerges once from a shelf occlusion gap and crosses | emergence_side | left, right |
|  |  | first_visible_distance_m | 1.2, 2.0 |
|  |  | gap_location | near, nominal, far |
|  |  | longitudinal_phase | early, nominal, late |
|  |  | pedestrian_speed_mps | 0.45, 0.7 |

Common density levels: low = 1 pedestrian(s), medium = 2 pedestrian(s), high = 4 pedestrian(s).
Current map note: map_empty is used only for early train/validation smoke; this is not map-disjoint generalization evidence.
