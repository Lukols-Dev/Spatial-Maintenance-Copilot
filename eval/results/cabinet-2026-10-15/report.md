# Evaluation on cabinet-2026-10-15

Atlas szafka2 v1, scored on the held-out view set szafka2-test. Every viewpoint shows the target hidden; its truth is the target clicked in the shot from the same spot with the target in sight.

|  |  |
|---|---|
| dataset manifest | `e1dcd7822f4fa08e` |
| Monte Carlo | 500 samples, seed 0 |
| click sigma | 1 px |
| agent's model | none |
| code | `4036635aafdb872101938dcadc5ae7c5140a36f2` with uncommitted changes |
| versions | Python 3.14.5, NumPy 2.5.3, OpenCV 5.0.0, LangGraph 1.2.15, arm64 |
| run | 2026-10-15T16:01:35+02:00 |

## Localisation

6 viewpoints, 6 with a truth, 6 of those localised with a 95% region.

| measure | n | median | p90 | max |
|---|---|---|---|---|
| target error, px | 6 | 11.2 | 94.7 | 110.3 |
| target error, accepted, px | 4 | 6.8 | 57.7 | 79.0 |
| error / target radius | 6 | 0.11 | 0.71 | 0.79 |
| RMS reprojection, px | 6 | 1.09 | 2.90 | 4.24 |
| RANSAC inlier ratio | 6 | 1.00 | 1.00 | 1.00 |
| 95% region, semi-major, px | 6 | 7.8 | 19.6 | 26.5 |

Truth inside the 95% region: 2/6 (33%, CI 10-70%); of the accepted results: 2/4 (50%, CI 15-85%).

Decisions: ACCEPT 4, MOVE_LEFT 1, MOVE_RIGHT 1.

| viewpoint | truth | landmarks | decision | inliers | RMS px | error px | target radius px | inside 95% | semi-major px |
|---|---|---|---|---|---|---|---|---|---|
| T1_close.png | T1_open.png | 24 | MOVE_RIGHT | 19 | 4.24 | 14.3 | 114.5 | no | 12.7 |
| T2_close.png | T2_open.png | 4 | MOVE_LEFT | 4 | 0.10 | 110.3 | 176.0 | no | 26.5 |
| T3_close.png | T3_open.png | 24 | ACCEPT | 24 | 0.60 | 79.0 | 100.6 | no | 6.5 |
| T4_close.png | T4_open.png | 28 | ACCEPT | 28 | 1.56 | 5.7 | 61.0 | yes | 6.9 |
| T5_close.png | T5_open.png | 16 | ACCEPT | 16 | 0.61 | 8.0 | 95.7 | no | 7.1 |
| T6_close.png | T6_open.png | 16 | ACCEPT | 16 | 1.57 | 2.4 | 91.0 | yes | 8.5 |

## Uncertainty calibration

How often the truth falls inside the region at each confidence, read from the squared Mahalanobis distance of the truth under the region's covariance.

| confidence | radius² | truth inside |
|---|---|---|
| 50% | 1.39 | 1/6 (17%, CI 3-56%) |
| 80% | 3.22 | 1/6 (17%, CI 3-56%) |
| 95% | 5.99 | 2/6 (33%, CI 10-70%) |
| 99% | 9.21 | 4/6 (67%, CI 30-90%) |

Median squared distance 7.84; a calibrated region gives 1.39. At the median the error is 2.38 times the spread the region assumes: the region is smaller than the errors need.

## Decisions against the truth

|  | truth inside | truth outside |
|---|---|---|
| accepted | 2 | 2 |
| asked to move | 0 | 2 |

No localisation: 0. False accepts: 2/4 (50%, CI 15-85%). Asked to move though the truth was inside: 0/2 (0%, CI 0-66%).

## Pose stability

Two shots from the same spot, 0 pairs both localised. Each shot was taken by hand, so a difference is the pose's error and the camera's own movement together.

| between the shots | n | median | p90 | max |
|---|---|---|---|---|
| camera centre, mm | 0 | - | - | - |
| rotation, deg | 0 | - | - | - |
| target, px | 0 | - | - | - |

| first | second | camera centre mm | rotation deg | target px |
|---|---|---|---|---|

The pose from the landmarks against the pose from the rig board in the same frame. In-sample frames are those the atlas was built from.

| frames | n | centre mm median | max | rotation deg median | max | target px median | max |
|---|---|---|---|---|---|---|---|
| held out | 3 | 55.6 | 87.5 | 2.34 | 3.72 | 6.5 | 10.9 |
| in-sample | 287 | 15.9 | 2276.6 | 0.73 | 135.36 | 3.1 | 769.8 |

| held-out frame | landmarks | board corners | centre mm | rotation deg | target px |
|---|---|---|---|---|---|
| T3_close.png | 24 | 15 | 87.5 | 3.72 | 6.5 |
| T3_open.png | 8 | 15 | 55.6 | 2.34 | 10.9 |
| T6_close.png | 16 | 15 | 12.2 | 0.72 | 4.4 |

Monte Carlo seeds 0, 1, 2, 3, 4 over 6 viewpoints: the region's semi-major axis varies by a median 5.3% (max 6.8%); the verdict on the truth changes in 0, the decision in 0.

## Task success

Sessions from every viewpoint, the operator simulated, at most 3 viewpoints each. Success: a result accepted with the truth inside its region. False accept: accepted with the truth outside. Refused: no result shown. A start is localised when its first view gives a 95% region.

| strategy |  |
|---|---|
| single_view | the first view's overlay, whatever its quality |
| policy_only | the first view's overlay if the policy accepts it, else nothing |
| agent | the agent's loop: move where it asks until it presents a result |
| random | the policy decides; the operator moves to a random viewpoint |

From every viewpoint:

| strategy | runs | success | false accept | refused | views to success, mean |
|---|---|---|---|---|---|
| single_view | 6 x 1 | 2/6 (33%, CI 10-70%) | 4/6 (67%, CI 30-90%) | 0/6 (0%, CI 0-39%) | 1.0 |
| policy_only | 6 x 1 | 2/6 (33%, CI 10-70%) | 2/6 (33%, CI 10-70%) | 2/6 (33%, CI 10-70%) | 1.0 |
| agent | 6 x 1 | 4/6 (67%, CI 30-90%) | 2/6 (33%, CI 10-70%) | 0/6 (0%, CI 0-39%) | 1.8 |
| random | 6 x 100 | 296/600 (49%) | 304/600 (51%) | 0/600 (0%) | 1.4 |

From the localised starts:

| strategy | runs | success | false accept | refused | views to success, mean |
|---|---|---|---|---|---|
| single_view | 6 x 1 | 2/6 (33%, CI 10-70%) | 4/6 (67%, CI 30-90%) | 0/6 (0%, CI 0-39%) | 1.0 |
| policy_only | 6 x 1 | 2/6 (33%, CI 10-70%) | 2/6 (33%, CI 10-70%) | 2/6 (33%, CI 10-70%) | 1.0 |
| agent | 6 x 1 | 4/6 (67%, CI 30-90%) | 2/6 (33%, CI 10-70%) | 0/6 (0%, CI 0-39%) | 1.8 |
| random | 6 x 100 | 296/600 (49%) | 304/600 (51%) | 0/600 (0%) | 1.4 |

From the not localised starts:

| strategy | runs | success | false accept | refused | views to success, mean |
|---|---|---|---|---|---|
| single_view | 0 x 1 | 0/0 | 0/0 | 0/0 | - |
| policy_only | 0 x 1 | 0/0 | 0/0 | 0/0 | - |
| agent | 0 x 1 | 0/0 | 0/0 | 0/0 | - |
| random | 0 x 100 | 0/0 | 0/0 | 0/0 | - |

Random runs share their start, so no interval is given for them.

The agent's model: none. Across its 6 sessions the guards corrected 0 of its outputs, and 9 turns took the policy's own words.

## The agent's next view

2 starts the policy asked to move from, with a truth; the agent named a viewpoint for 2. The random column is the mean over every other viewpoint.

| start | move | error px | semi-major px | agent's view | error px | semi-major px | accepted | random error px | random semi-major px | random accepted |
|---|---|---|---|---|---|---|---|---|---|---|
| T1_close.png | MOVE_RIGHT | 14.3 | 12.7 | T6_close.png | 2.4 | 8.5 | yes | 41.1 | 11.1 | 80% |
| T2_close.png | MOVE_LEFT | 110.3 | 26.5 | T1_close.png | 14.3 | 12.7 | no | 21.9 | 8.3 | 80% |

The agent's view lowers the error in 2/2 (100%, CI 34-100%), shrinks the region in 2/2 (100%, CI 34-100%) and is accepted in 1/2 (50%, CI 9-91%); a random view is accepted in 80%.

## Injected faults

Each fault over every viewpoint that localises and has a truth. Unsafe: accepted with the truth outside the region, an overlay in the wrong place.

The last column counts the trials whose target was drawn with the truth outside its region, accepted or not: what a system showing every overlay, without the policy, would have put in the wrong place.

| fault |  | trials | no result | asked to move | accepted, inside | unsafe | drawn, truth outside |
|---|---|---|---|---|---|---|---|
| none | the clicks as made: the reference | 6 | 0 | 2 | 2 | 2/6 (33%, CI 10-70%) | 4 |
| three_landmarks | one landmark short of a pose | 8448 | 8448 | 0 | 0 | 0/8448 (0%, CI 0-0%) | 0 |
| swapped_labels | two landmarks clicked under each other's name | 1176 | 0 | 281 | 498 | 397/1176 (34%, CI 31-37%) | 673 |
| gross_click | one click 60 px off, on the wrong feature | 112 | 0 | 28 | 44 | 40/112 (36%, CI 27-45%) | 68 |
| click_noise | every click off by the click sigma the region assumes | 60 | 0 | 20 | 21 | 19/60 (32%, CI 21-44%) | 39 |
| heavy_noise | every click off by three times that sigma | 60 | 0 | 56 | 2 | 2/60 (3%, CI 1-11%) | 36 |

## Traces

Every agent session's trace, perception to action, is in `traces/`, one file per start.
