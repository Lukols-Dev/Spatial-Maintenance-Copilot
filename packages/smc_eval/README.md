# smc-eval

The evaluation of the localisation loop on a frozen dataset. It runs the code the service runs (`smc_core`'s
`localise` and `decide`, `smc_core.viewpoints`, and the `smc_agent` Copilot graph) on inputs frozen in
`eval/datasets/`, so the numbers describe the system the web app shows.

- `dataset.py`: the frozen dataset. It holds the atlas, the clicks of each view set and the camera poses the
  rig board gives, plus a manifest with the SHA-256 of every frozen file, the camera file and the private
  media they came from. Loading checks every hash.
- `perception.py`: the agent's `Perception` over a frozen view set.
- `evaluate.py`: one run, every measure:
  - localisation error, reprojection and RANSAC inliers;
  - pose stability between two shots from one spot, and against the rig board;
  - uncertainty calibration, and the policy's decisions against the truth;
  - task success and the agent's next view, against a single view, the policy alone and a random view
    (`sessions.py`);
  - injected faults (`faults.py`).
- `check.py`: whether a new run reproduces stored results within fixed tolerances.
- `report.py`: the Markdown tables.

`tools/freeze_dataset.py` freezes a dataset, `tools/evaluate.py` runs the evaluation (`make eval`,
`make eval-check`). The tests (`tests/`) run on the synthetic scene of `smc_core.testing`.
