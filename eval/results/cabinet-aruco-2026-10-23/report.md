# Evaluation on cabinet-aruco-2026-10-23

Atlas cabinet-aruco v2, scored on the held-out view set cabinet-aruco-tripod. Every viewpoint shows the target hidden; its truth is the target clicked in the shot from the same spot with the target in sight.

|  |  |
|---|---|
| dataset manifest | `a0270e8057800a8e` |
| Monte Carlo | 500 samples, seed 0 |
| click sigma | 1 px |
| agent's model | none |
| code | `993157b21424ef2852810b101e6e3bc2ff8677a4` |
| versions | Python 3.14.5, NumPy 2.5.3, OpenCV 5.0.0, LangGraph 1.2.15, arm64 |
| run | 2026-10-23T15:04:52+02:00 |

## Localisation

27 viewpoints, 22 with a truth, 22 of those localised with a 95% region.

| measure | n | median | p90 | max |
|---|---|---|---|---|
| target error, px | 22 | 1.7 | 2.4 | 13.7 |
| target error, accepted, px | 18 | 1.6 | 2.2 | 2.5 |
| error / target radius | 22 | 0.02 | 0.03 | 0.09 |
| RMS reprojection, px | 27 | 0.77 | 2.05 | 2.38 |
| RANSAC inlier ratio | 27 | 1.00 | 1.00 | 1.00 |
| 95% region, semi-major, px | 22 | 6.3 | 9.6 | 98.0 |

Truth inside the 95% region: 22/22 (100%, CI 85-100%); of the accepted results: 18/18 (100%, CI 82-100%).

Decisions: ACCEPT 20, MOVE_LEFT 3, MOVE_RIGHT 3, MOVE_UP 1.

| viewpoint | truth | landmarks | decision | inliers | RMS px | error px | target radius px | inside 95% | semi-major px |
|---|---|---|---|---|---|---|---|---|---|
| T01_2_close.png | T01_open.png | 24 | ACCEPT | 24 | 0.59 | 1.1 | 79.6 | yes | 5.9 |
| T01_close.png | T01_open.png | 24 | ACCEPT | 24 | 0.64 | 0.8 | 79.6 | yes | 5.9 |
| T02_2_close.png | T02_open.png | 24 | ACCEPT | 24 | 0.77 | 1.1 | 77.8 | yes | 5.6 |
| T02_close.png | T02_open.png | 24 | ACCEPT | 24 | 0.74 | 0.7 | 77.8 | yes | 5.6 |
| T03_2_close.png | T03_open.png | 24 | ACCEPT | 24 | 0.73 | 1.6 | 83.5 | yes | 5.9 |
| T03_close.png | T03_open.png | 24 | ACCEPT | 24 | 0.76 | 2.0 | 83.5 | yes | 5.9 |
| T04_2_close.png | T04_open.png | 32 | ACCEPT | 32 | 1.74 | 1.2 | 75.4 | yes | 6.3 |
| T04_close.png | T04_open.png | 32 | ACCEPT | 32 | 1.68 | 1.6 | 75.3 | yes | 6.3 |
| T05_close.png | T05_open.png | 24 | ACCEPT | 24 | 0.86 | 1.3 | 82.4 | yes | 5.7 |
| T06_2_close.png | T06_open.png | 8 | MOVE_LEFT | 8 | 0.35 | 2.2 | 134.1 | yes | 9.7 |
| T06_close.png | T06_open.png | 8 | MOVE_LEFT | 8 | 0.64 | 1.8 | 134.2 | yes | 9.7 |
| T07_2_close.png | T07_open.png | 12 | ACCEPT | 12 | 0.43 | 2.5 | 121.9 | yes | 8.1 |
| T07_close.png | T07_open.png | 12 | ACCEPT | 12 | 0.49 | 1.7 | 121.8 | yes | 8.1 |
| T08_2_close.png | T08_open.png | 24 | ACCEPT | 24 | 0.86 | 1.6 | 47.5 | yes | 4.4 |
| T08_close.png | T08_open.png | 24 | ACCEPT | 24 | 0.77 | 1.1 | 47.7 | yes | 4.4 |
| T09_2_close.png | T09_open.png | 16 | ACCEPT | 16 | 2.00 | 2.1 | 80.1 | yes | 7.9 |
| T09_close.png | T09_open.png | 16 | ACCEPT | 15 | 1.88 | 2.5 | 80.1 | yes | 7.7 |
| T10_2_close.png | T10_open.png | 24 | ACCEPT | 24 | 0.58 | 1.7 | 100.0 | yes | 7.1 |
| T10_close.png | T10_open.png | 24 | ACCEPT | 24 | 0.56 | 1.8 | 100.1 | yes | 7.1 |
| T11_close.png | T11_open.png | 12 | MOVE_LEFT | 12 | 0.32 | 1.6 | 78.4 | yes | 8.3 |
| T12_close.png | T12_open.png | 24 | ACCEPT | 24 | 1.18 | 1.9 | 74.2 | yes | 5.3 |
| T13_2_close.png | - | 20 | ACCEPT | 20 | 1.24 | - | 130.5 | - | 8.9 |
| T13_close.png | - | 20 | ACCEPT | 20 | 1.23 | - | 130.5 | - | 8.9 |
| T15_2_close.png | - | 12 | MOVE_RIGHT | 8 | 2.29 | - | 151.9 | - | 35.1 |
| T15_close.png | - | 12 | MOVE_RIGHT | 8 | 2.38 | - | 151.9 | - | 35.1 |
| T16_close.png | - | 16 | MOVE_RIGHT | 12 | 2.12 | - | 101.7 | - | 28.1 |
| T17_close.png | T17_open.png | 4 | MOVE_UP | 4 | 0.11 | 13.7 | 153.1 | yes | 98.0 |

## Uncertainty calibration

How often the truth falls inside the region at each confidence, read from the squared Mahalanobis distance of the truth under the region's covariance.

| confidence | radius² | truth inside |
|---|---|---|
| 50% | 1.39 | 22/22 (100%, CI 85-100%) |
| 80% | 3.22 | 22/22 (100%, CI 85-100%) |
| 95% | 5.99 | 22/22 (100%, CI 85-100%) |
| 99% | 9.21 | 22/22 (100%, CI 85-100%) |

Median squared distance 0.33; a calibrated region gives 1.39. At the median the error is 0.49 of the spread the region assumes: the region is larger than the errors need, on the safe side.

## Decisions against the truth

|  | truth inside | truth outside |
|---|---|---|
| accepted | 18 | 0 |
| asked to move | 4 | 0 |

No localisation: 0. False accepts: 0/18 (0%, CI 0-18%). Asked to move though the truth was inside: 4/4 (100%, CI 51-100%).

## Pose stability

Two shots from the same spot, 11 pairs both localised. Each shot was taken by hand, so a difference is the pose's error and the camera's own movement together.

| between the shots | n | median | p90 | max |
|---|---|---|---|---|
| camera centre, mm | 11 | 1.0 | 7.6 | 14.3 |
| rotation, deg | 11 | 0.04 | 0.33 | 0.39 |
| target, px | 11 | 0.5 | 0.7 | 0.8 |

| first | second | camera centre mm | rotation deg | target px |
|---|---|---|---|---|
| T01_2_close.png | T01_close.png | 1.0 | 0.03 | 0.3 |
| T02_2_close.png | T02_close.png | 0.7 | 0.04 | 0.4 |
| T03_2_close.png | T03_close.png | 1.3 | 0.07 | 0.5 |
| T04_2_close.png | T04_close.png | 1.1 | 0.03 | 0.6 |
| T06_2_close.png | T06_close.png | 7.6 | 0.39 | 0.6 |
| T07_2_close.png | T07_close.png | 1.0 | 0.04 | 0.8 |
| T08_2_close.png | T08_close.png | 14.3 | 0.33 | 0.5 |
| T09_2_close.png | T09_close.png | 1.4 | 0.06 | 0.4 |
| T10_2_close.png | T10_close.png | 0.7 | 0.02 | 0.1 |
| T13_2_close.png | T13_close.png | 0.2 | 0.02 | 0.1 |
| T15_2_close.png | T15_close.png | 0.5 | 0.05 | 0.7 |

The pose from the landmarks against the pose from the rig board in the same frame. In-sample frames are those the atlas was built from.

| frames | n | centre mm median | max | rotation deg median | max | target px median | max |
|---|---|---|---|---|---|---|---|
| held out | 18 | 35.5 | 67.3 | 2.11 | 3.33 | 15.8 | 19.9 |
| in-sample | 252 | 15.9 | 2171.5 | 0.73 | 137.35 | 3.2 | 769.3 |

| held-out frame | landmarks | board corners | centre mm | rotation deg | target px |
|---|---|---|---|---|---|
| T01_2_close.png | 24 | 13 | 61.0 | 2.83 | 19.6 |
| T01_close.png | 24 | 13 | 50.8 | 2.64 | 19.9 |
| T01_open.png | 8 | 11 | 37.4 | 2.18 | 17.1 |
| T02_2_close.png | 24 | 10 | 35.0 | 2.11 | 16.9 |
| T02_close.png | 24 | 11 | 35.2 | 2.12 | 17.3 |
| T02_open.png | 8 | 13 | 33.8 | 2.06 | 16.8 |
| T03_2_close.png | 24 | 10 | 33.3 | 2.28 | 17.9 |
| T03_close.png | 24 | 10 | 35.7 | 2.24 | 17.2 |
| T03_open.png | 8 | 11 | 20.8 | 2.01 | 15.6 |
| T04_2_close.png | 32 | 9 | 22.7 | 1.91 | 16.0 |
| T04_close.png | 32 | 8 | 31.1 | 1.86 | 15.5 |
| T09_2_close.png | 16 | 15 | 40.8 | 1.89 | 14.7 |
| T09_close.png | 16 | 14 | 40.7 | 1.86 | 14.2 |
| T10_2_close.png | 24 | 15 | 58.4 | 2.90 | 12.9 |
| T10_close.png | 24 | 15 | 67.3 | 3.33 | 12.8 |
| T10_open.png | 8 | 15 | 49.9 | 2.47 | 10.6 |
| T11_close.png | 12 | 10 | 32.9 | 1.26 | 11.9 |
| T11_open.png | 4 | 10 | 12.2 | 0.51 | 8.7 |

Monte Carlo seeds 0, 1, 2, 3, 4 over 27 viewpoints: the region's semi-major axis varies by a median 4.7% (max 18.3%); the verdict on the truth changes in 0, the decision in 0.

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
| single_view | 27 x 1 | 22/22 (100%, CI 85-100%) | 0/22 (0%, CI 0-15%) | 0/27 (0%, CI 0-12%) | 1.0 |
| policy_only | 27 x 1 | 18/25 (72%, CI 52-86%) | 0/25 (0%, CI 0-13%) | 7/27 (26%, CI 13-45%) | 1.0 |
| agent | 27 x 1 | 25/25 (100%, CI 87-100%) | 0/25 (0%, CI 0-13%) | 0/27 (0%, CI 0-12%) | 1.3 |
| random | 27 x 100 | 2426/2430 (100%) | 0/2430 (0%) | 4/2700 (0%) | 1.3 |

From the localised starts:

| strategy | runs | success | false accept | refused | views to success, mean |
|---|---|---|---|---|---|
| single_view | 27 x 1 | 22/22 (100%, CI 85-100%) | 0/22 (0%, CI 0-15%) | 0/27 (0%, CI 0-12%) | 1.0 |
| policy_only | 27 x 1 | 18/25 (72%, CI 52-86%) | 0/25 (0%, CI 0-13%) | 7/27 (26%, CI 13-45%) | 1.0 |
| agent | 27 x 1 | 25/25 (100%, CI 87-100%) | 0/25 (0%, CI 0-13%) | 0/27 (0%, CI 0-12%) | 1.3 |
| random | 27 x 100 | 2426/2430 (100%) | 0/2430 (0%) | 4/2700 (0%) | 1.3 |

From the not localised starts:

| strategy | runs | success | false accept | refused | views to success, mean |
|---|---|---|---|---|---|
| single_view | 0 x 1 | 0/0 | 0/0 | 0/0 | - |
| policy_only | 0 x 1 | 0/0 | 0/0 | 0/0 | - |
| agent | 0 x 1 | 0/0 | 0/0 | 0/0 | - |
| random | 0 x 100 | 0/0 | 0/0 | 0/0 | - |

Random runs share their start, so no interval is given for them.

The agent's model: none. Across its 27 sessions the guards corrected 0 of its outputs, and 35 turns took the policy's own words.

## The agent's next view

4 starts the policy asked to move from, with a truth; the agent named a viewpoint for 4. The random column is the mean over every other viewpoint.

| start | move | error px | semi-major px | agent's view | error px | semi-major px | accepted | random error px | random semi-major px | random accepted |
|---|---|---|---|---|---|---|---|---|---|---|
| T06_2_close.png | MOVE_LEFT | 2.2 | 9.7 | T07_2_close.png | 2.5 | 8.1 | yes | 2.2 | 13.3 | 77% |
| T06_close.png | MOVE_LEFT | 1.8 | 9.7 | T07_2_close.png | 2.5 | 8.1 | yes | 2.2 | 13.3 | 77% |
| T11_close.png | MOVE_LEFT | 1.6 | 8.3 | T04_2_close.png | 1.2 | 6.3 | yes | 2.2 | 13.3 | 77% |
| T17_close.png | MOVE_UP | 13.7 | 98.0 | T06_close.png | 1.8 | 9.7 | no | 1.6 | 9.9 | 77% |

The agent's view lowers the error in 2/4 (50%, CI 15-85%), shrinks the region in 4/4 (100%, CI 51-100%) and is accepted in 3/4 (75%, CI 30-95%); a random view is accepted in 77%.

## Injected faults

Each fault over every viewpoint that localises and has a truth. Unsafe: accepted with the truth outside the region, an overlay in the wrong place.

The last column counts the trials whose target was drawn with the truth outside its region, accepted or not: what a system showing every overlay, without the policy, would have put in the wrong place.

| fault |  | trials | no result | asked to move | accepted, inside | unsafe | drawn, truth outside |
|---|---|---|---|---|---|---|---|
| none | the clicks as made: the reference | 22 | 0 | 4 | 18 | 0/22 (0%, CI 0-15%) | 0 |
| three_landmarks | one landmark short of a pose | 36104 | 36104 | 0 | 0 | 0/36104 (0%, CI 0-0%) | 0 |
| swapped_labels | two landmarks clicked under each other's name | 4804 | 0 | 128 | 4676 | 0/4804 (0%, CI 0-0%) | 8 |
| gross_click | one click 60 px off, on the wrong feature | 440 | 0 | 32 | 408 | 0/440 (0%, CI 0-1%) | 4 |
| click_noise | every click off by the click sigma the region assumes | 220 | 0 | 40 | 180 | 0/220 (0%, CI 0-2%) | 0 |
| heavy_noise | every click off by three times that sigma | 220 | 0 | 214 | 6 | 0/220 (0%, CI 0-2%) | 13 |

## Traces

Every agent session's trace, perception to action, is in `traces/`, one file per start.
