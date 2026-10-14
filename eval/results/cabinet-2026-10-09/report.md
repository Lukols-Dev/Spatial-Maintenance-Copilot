# Evaluation on cabinet-2026-10-09

Atlas szafka v2, scored on the held-out view set szafka-b. Every viewpoint shows the target hidden; its truth is the target clicked in the shot from the same spot with the target in sight.

|  |  |
|---|---|
| dataset manifest | `f50c06b7c3b1b1e0` |
| Monte Carlo | 500 samples, seed 0 |
| click sigma | 2 px |
| agent's model | none |
| code | `2e6bd904bb246d7ab223dcca058b555fb6b60697` with uncommitted changes |
| versions | Python 3.14.5, NumPy 2.5.3, OpenCV 5.0.0, LangGraph 1.2.15, arm64 |
| run | 2026-10-14T01:19:46+02:00 |

## Localisation

19 viewpoints, 14 with a truth, 12 of those localised with a 95% region.

| measure | n | median | p90 | max |
|---|---|---|---|---|
| target error, px | 12 | 3.4 | 7.9 | 13.8 |
| target error, accepted, px | 4 | 2.5 | 3.5 | 3.9 |
| error / target radius | 12 | 0.03 | 0.09 | 0.11 |
| RMS reprojection, px | 12 | 0.58 | 2.42 | 2.64 |
| RANSAC inlier ratio | 12 | 1.00 | 1.00 | 1.00 |
| 95% region, semi-major, px | 12 | 17.1 | 21.2 | 21.6 |

Truth inside the 95% region: 12/12 (100%, CI 76-100%); of the accepted results: 4/4 (100%, CI 51-100%).

Decisions: ACCEPT 4, MOVE_BACK 7, MOVE_CLOSER 2, MOVE_LEFT 6.

| viewpoint | truth | landmarks | decision | inliers | RMS px | error px | target radius px | inside 95% | semi-major px |
|---|---|---|---|---|---|---|---|---|---|
| B1_1_close.png | B1_open.png | 4 | MOVE_LEFT | 4 | 0.41 | 3.8 | 96.1 | yes | 18.2 |
| B1_close.png | B1_open.png | 4 | MOVE_LEFT | 4 | 0.51 | 1.8 | 96.0 | yes | 18.2 |
| B2_1_close.png | B2_open.png | 6 | MOVE_CLOSER | 5 | 2.60 | 1.8 | 90.1 | yes | 15.8 |
| B2_close.png | B2_open.png | 6 | MOVE_CLOSER | 5 | 2.64 | 8.2 | 88.4 | yes | 15.4 |
| B3_1_close.png | B3_open.png | 4 | MOVE_LEFT | 4 | 0.49 | 3.6 | 88.5 | yes | 16.0 |
| B3_close.png | B3_open.png | 4 | MOVE_LEFT | 4 | 0.52 | 4.4 | 88.6 | yes | 16.0 |
| B4_1_close.png | B4_open.png | 4 | MOVE_LEFT | 4 | 0.80 | 13.8 | 121.6 | yes | 21.6 |
| B4_close.png | B4_open.png | 4 | MOVE_LEFT | 4 | 0.41 | 3.3 | 121.1 | yes | 21.5 |
| B5_1_close.png | B5_open.png | 6 | ACCEPT | 6 | 0.82 | 2.4 | 107.4 | yes | 18.5 |
| B5_close.png | B5_open.png | 6 | ACCEPT | 6 | 0.71 | 3.9 | 107.4 | yes | 18.5 |
| B6_1_close.png | - | 1 | too_few_correspondences | - | - | - | - | - | - |
| B6_close.png | - | 1 | too_few_correspondences | - | - | - | - | - | - |
| B6_open.png | - | 1 | too_few_correspondences | - | - | - | - | - | - |
| B7_1_close.png | B7_open.png | 6 | ACCEPT | 6 | 0.64 | 1.4 | 92.7 | yes | 15.5 |
| B7_close.png | B7_open.png | 6 | ACCEPT | 6 | 0.47 | 2.7 | 92.7 | yes | 15.5 |
| B8_1_close.png | B8_open.png | 3 | too_few_correspondences | - | - | - | - | - | - |
| B8_close.png | B8_open.png | 3 | too_few_correspondences | - | - | - | - | - | - |
| B9_1_close.png | - | 2 | too_few_correspondences | - | - | - | - | - | - |
| B9_close.png | - | 2 | too_few_correspondences | - | - | - | - | - | - |

## Uncertainty calibration

How often the truth falls inside the region at each confidence, read from the squared Mahalanobis distance of the truth under the region's covariance.

| confidence | radius² | truth inside |
|---|---|---|
| 50% | 1.39 | 10/12 (83%, CI 55-95%) |
| 80% | 3.22 | 12/12 (100%, CI 76-100%) |
| 95% | 5.99 | 12/12 (100%, CI 76-100%) |
| 99% | 9.21 | 12/12 (100%, CI 76-100%) |

Median squared distance 0.23; a calibrated region gives 1.39. At the median the error is 0.41 of the spread the region assumes: the region is larger than the errors need, on the safe side.

## Decisions against the truth

|  | truth inside | truth outside |
|---|---|---|
| accepted | 4 | 0 |
| asked to move | 8 | 0 |

No localisation: 2. False accepts: 0/4 (0%, CI 0-49%). Asked to move though the truth was inside: 8/8 (100%, CI 68-100%).

## Pose stability

Two shots from the same spot, 6 pairs both localised. Each shot was taken by hand, so a difference is the pose's error and the camera's own movement together.

| between the shots | n | median | p90 | max |
|---|---|---|---|---|
| camera centre, mm | 6 | 5.7 | 47.5 | 81.6 |
| rotation, deg | 6 | 0.38 | 1.93 | 3.36 |
| target, px | 6 | 4.0 | 11.6 | 15.4 |

| first | second | camera centre mm | rotation deg | target px |
|---|---|---|---|---|
| B1_1_close.png | B1_close.png | 13.3 | 0.45 | 4.4 |
| B2_1_close.png | B2_close.png | 81.6 | 3.36 | 7.7 |
| B3_1_close.png | B3_close.png | 6.8 | 0.31 | 1.0 |
| B4_1_close.png | B4_close.png | 3.1 | 0.50 | 15.4 |
| B5_1_close.png | B5_close.png | 4.5 | 0.27 | 3.4 |
| B7_1_close.png | B7_close.png | 2.0 | 0.06 | 3.6 |

The pose from the landmarks against the pose from the rig board in the same frame. In-sample frames are those the atlas was built from.

| frames | n | centre mm median | max | rotation deg median | max | target px median | max |
|---|---|---|---|---|---|---|---|
| held out | 2 | 5.7 | 5.9 | 0.23 | 0.24 | 2.1 | 2.4 |
| in-sample | 53 | 10.1 | 22.8 | 0.43 | 0.97 | 1.4 | 5.0 |

| held-out frame | landmarks | board corners | centre mm | rotation deg | target px |
|---|---|---|---|---|---|
| B7_1_close.png | 6 | 15 | 5.6 | 0.24 | 2.4 |
| B7_close.png | 6 | 15 | 5.9 | 0.22 | 1.7 |

Monte Carlo seeds 0, 1, 2, 3, 4 over 12 viewpoints: the region's semi-major axis varies by a median 9.0% (max 12.3%); the verdict on the truth changes in 0, the decision in 0.

## Task success

Sessions from every viewpoint, the operator simulated, at most 4 viewpoints each. Success: a result accepted with the truth inside its region. False accept: accepted with the truth outside. Refused: no result shown. A start is localised when its first view gives a 95% region.

| strategy |  |
|---|---|
| single_view | the first view's overlay, whatever its quality |
| policy_only | the first view's overlay if the policy accepts it, else nothing |
| agent | the agent's loop: move where it asks until it presents a result |
| random | the policy decides; the operator moves to a random viewpoint |

From every viewpoint:

| strategy | runs | success | false accept | refused | views to success, mean |
|---|---|---|---|---|---|
| single_view | 19 x 1 | 12/19 (63%, CI 41-81%) | 0/19 (0%, CI 0-17%) | 7/19 (37%, CI 19-59%) | 1.0 |
| policy_only | 19 x 1 | 4/19 (21%, CI 9-43%) | 0/19 (0%, CI 0-17%) | 15/19 (79%, CI 57-91%) | 1.0 |
| agent | 19 x 1 | 12/19 (63%, CI 41-81%) | 0/19 (0%, CI 0-17%) | 7/19 (37%, CI 19-59%) | 2.2 |
| random | 19 x 100 | 1218/1900 (64%) | 0/1900 (0%) | 682/1900 (36%) | 2.2 |

From the localised starts:

| strategy | runs | success | false accept | refused | views to success, mean |
|---|---|---|---|---|---|
| single_view | 12 x 1 | 12/12 (100%, CI 76-100%) | 0/12 (0%, CI 0-24%) | 0/12 (0%, CI 0-24%) | 1.0 |
| policy_only | 12 x 1 | 4/12 (33%, CI 14-61%) | 0/12 (0%, CI 0-24%) | 8/12 (67%, CI 39-86%) | 1.0 |
| agent | 12 x 1 | 12/12 (100%, CI 76-100%) | 0/12 (0%, CI 0-24%) | 0/12 (0%, CI 0-24%) | 2.2 |
| random | 12 x 100 | 827/1200 (69%) | 0/1200 (0%) | 373/1200 (31%) | 2.0 |

From the not localised starts:

| strategy | runs | success | false accept | refused | views to success, mean |
|---|---|---|---|---|---|
| single_view | 7 x 1 | 0/7 (0%, CI 0-35%) | 0/7 (0%, CI 0-35%) | 7/7 (100%, CI 65-100%) | - |
| policy_only | 7 x 1 | 0/7 (0%, CI 0-35%) | 0/7 (0%, CI 0-35%) | 7/7 (100%, CI 65-100%) | - |
| agent | 7 x 1 | 0/7 (0%, CI 0-35%) | 0/7 (0%, CI 0-35%) | 7/7 (100%, CI 65-100%) | - |
| random | 7 x 100 | 391/700 (56%) | 0/700 (0%) | 309/700 (44%) | 2.8 |

Random runs share their start, so no interval is given for them.

The agent's model: none. Across its 19 sessions the guards corrected 0 of its outputs, and 33 turns took the policy's own words.

## The agent's next view

8 starts the policy asked to move from, with a truth; the agent named a viewpoint for 8. The random column is the mean over every other viewpoint.

| start | move | error px | semi-major px | agent's view | error px | semi-major px | accepted | random error px | random semi-major px | random accepted |
|---|---|---|---|---|---|---|---|---|---|---|
| B1_1_close.png | MOVE_LEFT | 3.8 | 18.2 | B2_1_close.png | 1.8 | 15.8 | no | 4.3 | 17.5 | 22% |
| B1_close.png | MOVE_LEFT | 1.8 | 18.2 | B2_1_close.png | 1.8 | 15.8 | no | 4.5 | 17.5 | 22% |
| B2_1_close.png | MOVE_CLOSER | 1.8 | 15.8 | B5_1_close.png | 2.4 | 18.5 | yes | 4.5 | 17.7 | 22% |
| B2_close.png | MOVE_CLOSER | 8.2 | 15.4 | B5_1_close.png | 2.4 | 18.5 | yes | 3.9 | 17.7 | 22% |
| B3_1_close.png | MOVE_LEFT | 3.6 | 16.0 | B1_close.png | 1.8 | 18.2 | no | 4.3 | 17.7 | 22% |
| B3_close.png | MOVE_LEFT | 4.4 | 16.0 | B1_close.png | 1.8 | 18.2 | no | 4.2 | 17.7 | 22% |
| B4_1_close.png | MOVE_LEFT | 13.8 | 21.6 | B5_1_close.png | 2.4 | 18.5 | yes | 3.4 | 17.2 | 22% |
| B4_close.png | MOVE_LEFT | 3.3 | 21.5 | B5_1_close.png | 2.4 | 18.5 | yes | 4.3 | 17.2 | 22% |

The agent's view lowers the error in 7/8 (88%, CI 53-98%), shrinks the region in 4/8 (50%, CI 22-78%) and is accepted in 4/8 (50%, CI 22-78%); a random view is accepted in 22%.

## Injected faults

Each fault over every viewpoint that localises and has a truth. Unsafe: accepted with the truth outside the region, an overlay in the wrong place.

The last column counts the trials whose target was drawn with the truth outside its region, accepted or not: what a system showing every overlay, without the policy, would have put in the wrong place.

| fault |  | trials | no result | asked to move | accepted, inside | unsafe | drawn, truth outside |
|---|---|---|---|---|---|---|---|
| none | the clicks as made: the reference | 12 | 0 | 8 | 4 | 0/12 (0%, CI 0-24%) | 0 |
| three_landmarks | one landmark short of a pose | 144 | 144 | 0 | 0 | 0/144 (0%, CI 0-3%) | 0 |
| swapped_labels | two landmarks clicked under each other's name | 126 | 90 | 36 | 0 | 0/126 (0%, CI 0-3%) | 34 |
| gross_click | one click 60 px off, on the wrong feature | 60 | 9 | 51 | 0 | 0/60 (0%, CI 0-6%) | 24 |
| click_noise | every click off by the click sigma the region assumes | 120 | 0 | 81 | 39 | 0/120 (0%, CI 0-3%) | 0 |
| heavy_noise | every click off by three times that sigma | 120 | 11 | 105 | 4 | 0/120 (0%, CI 0-3%) | 4 |

## Traces

Every agent session's trace, perception to action, is in `traces/`, one file per start.
