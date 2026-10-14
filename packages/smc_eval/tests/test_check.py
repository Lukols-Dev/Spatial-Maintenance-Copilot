"""Reproducing stored results: what may move, and by how much."""

import copy
from typing import Any

from smc_eval.check import differences

STORED = {
    "evaluated_at": "2026-10-14T00:00:00+02:00",
    "environment": {"machine": "arm64"},
    "localisation": {"error_px": {"median": 3.4, "n": 12}, "inside_95": {"k": 12, "rate": 1.0}},
    "repeats": [{"first": "B1_close.png", "translation_mm": 13.3, "rotation_deg": 0.45}],
    "monte_carlo": {"semi_major_relative_spread": {"median": 0.09}},
    "views": [{"view": "B1_close.png", "reliable": False}],
}


def changed(path: list[str | int], value: object) -> dict[str, Any]:
    """STORED with one value replaced, at its path."""
    other: dict[str, Any] = copy.deepcopy(STORED)
    target: Any = other
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return other


def test_the_same_results_reproduce() -> None:
    assert differences(STORED, STORED) == []


def test_when_and_where_the_run_was_made_is_not_compared() -> None:
    other = changed(["environment", "machine"], "x86_64")
    other["evaluated_at"] = "2026-10-20T00:00:00+02:00"

    assert differences(STORED, other) == []


def test_a_number_with_a_unit_moves_within_its_tolerance() -> None:
    assert differences(STORED, changed(["localisation", "error_px", "median"], 3.8)) == []
    assert differences(STORED, changed(["repeats", 0, "translation_mm"], 14.2)) == []
    assert differences(STORED, changed(["repeats", 0, "rotation_deg"], 0.6)) == []


def test_a_number_beyond_its_tolerance_is_named_by_its_path() -> None:
    found = differences(STORED, changed(["localisation", "error_px", "median"], 4.0))

    assert found == ["localisation.error_px.median: 3.4, now 4.0"]


def test_a_number_without_a_unit_moves_by_a_share_of_itself() -> None:
    assert (
        differences(
            STORED, changed(["monte_carlo", "semi_major_relative_spread", "median"], 0.0901)
        )
        == []
    )
    assert (
        differences(STORED, changed(["monte_carlo", "semi_major_relative_spread", "median"], 0.1))
        != []
    )


def test_counts_verdicts_and_names_must_match() -> None:
    assert differences(STORED, changed(["localisation", "inside_95", "k"], 11)) == [
        "localisation.inside_95.k: 12, now 11"
    ]
    assert differences(STORED, changed(["views", 0, "reliable"], True)) == [
        "views[0].reliable: False, now True"
    ]
    assert differences(STORED, changed(["repeats", 0, "first"], "B2_close.png")) != []


def test_items_gone_or_new_are_named() -> None:
    assert differences(STORED, changed(["views"], [])) == ["views: 1 items, now 0"]
    assert differences(STORED, changed(["localisation", "added"], 1)) == ["localisation.added: new"]
