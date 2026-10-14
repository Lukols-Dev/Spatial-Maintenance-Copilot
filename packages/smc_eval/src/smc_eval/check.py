"""Whether a new run reproduces stored results, within tolerances fixed in advance.

The evaluation plan asks for results numerically reproducible within
predefined tolerances, not bit-identical across hardware: the solvers and the
Monte Carlo region may round differently on another CPU. A measure in pixels
may move by TOLERANCES["_px"], in millimetres by TOLERANCES["_mm"], in degrees
by TOLERANCES["_deg"]; any other number by RELATIVE of itself. Counts, verdicts
and names must match exactly: a view that turns from accepted to held is a
changed result, whatever the reason. When and where the run was made is not
compared.
"""

import re
from typing import Any

TOLERANCES = {"_px": 0.5, "_mm": 1.0, "_deg": 0.2}
RELATIVE = 0.02
NOT_COMPARED = {"evaluated_at", "environment"}


def differences(expected: Any, actual: Any, path: str = "") -> list[str]:
    """Every place actual departs from expected beyond its tolerance, by its path in the results."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        found = []
        for key in sorted(expected.keys() | actual.keys()):
            if key in NOT_COMPARED:
                continue
            where = f"{path}.{key}" if path else key
            if key not in actual:
                found.append(f"{where}: gone")
            elif key not in expected:
                found.append(f"{where}: new")
            else:
                found += differences(expected[key], actual[key], where)
        return found
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path}: {len(expected)} items, now {len(actual)}"]
        return [
            difference
            for index, (old, new) in enumerate(zip(expected, actual, strict=True))
            for difference in differences(old, new, f"{path}[{index}]")
        ]
    if _number(expected) and _number(actual):
        if abs(actual - expected) <= tolerance(path, expected):
            return []
        return [f"{path}: {expected}, now {actual}"]
    return [] if expected == actual else [f"{path}: {expected!r}, now {actual!r}"]


def tolerance(path: str, expected: float) -> float:
    """The tolerance of the nearest name on the path with a unit; integers have none."""
    if isinstance(expected, int):
        return 0.0
    for name in reversed(re.sub(r"\[\d+\]", "", path).split(".")):
        for suffix, allowed in TOLERANCES.items():
            if name.endswith(suffix):
                return allowed
    return RELATIVE * abs(expected)


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
