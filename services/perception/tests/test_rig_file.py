"""The line editor behind PUT /boards/{id}/measurement, on layouts the generator never writes."""

from datetime import date

import pytest
import yaml
from smc_perception.rig_file import LayoutError, edit_board, yaml_scalar

RIG = """\
boards:
  a:
    square_measured_mm: null # one square
    substrate: 'it''s glued'   # a comment
    measured_on:
  b:
    square_measured_mm: null
"""


def test_values_are_replaced_where_they_stand_keeping_comments() -> None:
    edited = edit_board(
        RIG, "a", {"square_measured_mm": "25.0", "substrate": '"x"', "measured_on": "2026-10-06"}
    )

    assert (
        edited
        == """\
boards:
  a:
    square_measured_mm: 25.0 # one square
    substrate: "x"   # a comment
    measured_on: 2026-10-06
  b:
    square_measured_mm: null
"""
    )


def test_a_key_the_board_lacks_is_added_after_its_last_key() -> None:
    edited = edit_board(RIG, "b", {"substrate": "null"})

    assert edited == RIG + "    substrate: null\n"


@pytest.mark.parametrize(
    "rig",
    [
        "boards: {a: {square_measured_mm: null}}\n",
        "boards:\n  'a':\n    square_measured_mm: null\n",
        "boards:\n  a:\n    square_measured_mm: *anchor\n",
        'boards:\n  a:\n    square_measured_mm: "two\n      lines"\n',
        "boards:\n  a:\n    square_measured_mm:\n      - 1\n",
        "board:\n  a:\n    square_measured_mm: null\n",
    ],
)
def test_a_layout_it_cannot_edit_is_refused(rig: str) -> None:
    with pytest.raises(LayoutError):
        edit_board(rig, "a", {"square_measured_mm": "25.0"})


@pytest.mark.parametrize(
    "value", [25.02, 0.02, 1e-05, 1e20, None, date(2026, 10, 6), 'a "b" \\ c', "null", "", "ü\n✓"]
)
def test_a_scalar_reads_back_as_itself(value: float | str | date | None) -> None:
    token = yaml_scalar(value)

    assert "\n" not in token
    assert yaml.safe_load(f"key: {token}\n") == {"key": value}
