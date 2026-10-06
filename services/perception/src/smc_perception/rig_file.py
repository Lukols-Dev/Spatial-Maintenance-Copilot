"""calib/rig.yaml: the printed boards, read for the API and edited in place.

The file is the user's, written by gen_charuco_boards.py and then by hand,
with comments that explain it. A measurement therefore rewrites only the
values of one board's measurement keys, line by line, and leaves every other
byte alone; a YAML dump would drop the comments and reorder the keys. The
edited text is parsed again before it replaces the file, and must load as the
old file with exactly those values changed.
"""

import copy
import re
import threading
from collections.abc import Mapping
from datetime import date
from typing import Any, NamedTuple

import cv2 as cv
import yaml
from pydantic import ValidationError
from smc_core.rig import RigBoard, load_rig_board

from smc_perception.errors import Conflict, Invalid, NotFound, WorkspaceError, describe
from smc_perception.models import Board, BoardMeasurement, Rig
from smc_perception.workspace import WorkspaceFiles, write_atomic

# A typed value further than this from the nominal square is most likely the
# length of several squares, or a marker side, not one square side.
PLAUSIBLE_SCALE = (0.8, 1.25)

_KEY_LINE = re.compile(r"(?P<indent> *)(?P<key>[A-Za-z0-9_.-]+):(?P<rest>(?:[ \t].*)?)")
# PyYAML keeps a long double-quoted string on one line only below this width.
_ONE_LINE = 1 << 30
# One rig file edit at a time: endpoints run in a thread pool.
_lock = threading.Lock()


# ---- reading -----------------------------------------------------------------


def read_rig(workspace: WorkspaceFiles) -> Rig:
    """Every board of the rig file; a problem with the file or a board is in error."""
    try:
        _, data = _load(workspace)
    except (NotFound, Conflict) as error:
        return Rig(dictionary=None, boards=[], error=str(error))
    return _rig_from_yaml(data, workspace.relative(workspace.rig_file))


def _rig_from_yaml(data: object, name: str) -> Rig:
    if not isinstance(data, dict) or not isinstance(data.get("boards"), dict):
        return Rig(dictionary=None, boards=[], error=f"{name} has no boards")

    problems = []
    dictionary = data.get("dictionary")
    if not isinstance(dictionary, str) or not hasattr(cv.aruco, dictionary):
        problems.append(f"unknown marker dictionary {dictionary!r}")
        dictionary = None
    boards = []
    for board_id, entry in data["boards"].items():
        try:
            boards.append(board_from_yaml(str(board_id), entry))
        except ValueError as error:
            problems.append(f"board {board_id}: {error}")
    return Rig(dictionary=dictionary, boards=boards, error="; ".join(problems) or None)


def board_from_yaml(board_id: str, entry: object) -> Board:
    """One board entry of the rig file. Raises ValueError saying what is wrong."""
    if not isinstance(entry, dict):
        raise ValueError("not a mapping of keys")
    try:
        first, last = entry["ids"]
        return Board(
            id=board_id,
            squares_x=entry["squares_x"],
            squares_y=entry["squares_y"],
            marker_ids=(first, last),
            square_nominal_mm=entry["square_nominal_mm"],
            marker_nominal_mm=entry["marker_nominal_mm"],
            square_measured_mm=entry.get("square_measured_mm"),
            marker_measured_mm=entry.get("marker_measured_mm"),
            measurement_uncertainty_mm=entry.get("measurement_uncertainty_mm"),
            substrate=entry.get("substrate"),
            measured_on=entry.get("measured_on"),
            measured=entry.get("square_measured_mm") is not None,
        )
    except KeyError as error:
        raise ValueError(f"no {error.args[0]}") from error
    except (TypeError, ValueError) as error:
        message = (
            describe(error) if isinstance(error, ValidationError) else "ids is not [first, last]"
        )
        raise ValueError(message) from error


def measured_board(workspace: WorkspaceFiles, board_id: str) -> RigBoard:
    """A board ready for posing, read the way the atlas CLI reads it.

    404 when the board is not in the rig file, 409 when it is not measured.
    """
    name = workspace.relative(workspace.rig_file)
    board = _board(name, _load(workspace)[1], board_id)
    if not board.measured:
        raise Conflict(f"board {board_id!r} is not measured: square_measured_mm is null")
    try:
        return load_rig_board(workspace.rig_file, board_id)
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise Conflict(f"cannot use board {board_id!r} of {name}: {_reason(error)}") from error


def _load(workspace: WorkspaceFiles) -> tuple[str, Any]:
    """Text and content of the rig file: 404 when it is missing, 409 when it does not load."""
    path = workspace.rig_file
    name = workspace.relative(path)
    if not path.is_file():
        raise NotFound(f"{name} not found")
    try:
        text = path.read_bytes().decode("utf-8")
        return text, yaml.safe_load(text)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as error:
        raise Conflict(f"cannot read {name}: {_reason(error)}") from error


def _board(name: str, data: Any, board_id: str) -> Board:
    boards = data.get("boards") if isinstance(data, dict) else None
    if not isinstance(boards, dict) or board_id not in boards:
        raise NotFound(f"no board named {board_id!r} in {name}")
    try:
        return board_from_yaml(board_id, boards[board_id])
    except ValueError as error:
        raise Conflict(f"board {board_id!r} in {name}: {error}") from error


def _reason(error: Exception) -> str:
    if isinstance(error, yaml.MarkedYAMLError) and error.problem_mark is not None:
        return f"{error.problem} (line {error.problem_mark.line + 1})"
    if isinstance(error, UnicodeDecodeError):
        return "not UTF-8 text"
    if isinstance(error, OSError):
        return "cannot read the file"
    return str(error)


# ---- measuring ---------------------------------------------------------------


def measure_board(workspace: WorkspaceFiles, board_id: str, measurement: BoardMeasurement) -> Board:
    """Write a caliper reading into the board's entry and return the board as stored."""
    name = workspace.relative(workspace.rig_file)
    with _lock:
        text, before = _load(workspace)
        check_plausible(_board(name, before, board_id), measurement.square_measured_mm)

        values: dict[str, Any] = {
            "square_measured_mm": measurement.square_measured_mm,
            "marker_measured_mm": measurement.marker_measured_mm,
            "measurement_uncertainty_mm": measurement.measurement_uncertainty_mm,
            "substrate": measurement.substrate,
            "measured_on": measurement.measured_on or date.today(),
        }
        expected = copy.deepcopy(before)
        expected["boards"][board_id].update(values)
        try:
            edited = edit_board(text, board_id, {key: yaml_scalar(v) for key, v in values.items()})
            if yaml.safe_load(edited) != expected:
                raise LayoutError("the edited file does not load as the measured board")
        except (LayoutError, yaml.YAMLError) as error:
            raise WorkspaceError(
                f"cannot edit {name} in place: {error}; it is unchanged"
            ) from error
        write_atomic(workspace.rig_file, edited.encode("utf-8"))

    return board_from_yaml(board_id, expected["boards"][board_id])


def check_plausible(board: Board, square_mm: float) -> None:
    low, high = (scale * board.square_nominal_mm for scale in PLAUSIBLE_SCALE)
    if not low <= square_mm <= high:
        raise Invalid(
            f"square_measured_mm {square_mm:g} mm is far from the nominal square of "
            f"{board.square_nominal_mm:g} mm (expected {low:g} to {high:g}): "
            "measure the side of one square"
        )


def yaml_scalar(value: float | str | date | None) -> str:
    """value as one YAML token on one line, written the way PyYAML reads it back.

    Strings are always double-quoted, with PyYAML's own escaping. Floats keep
    a decimal point: PyYAML reads 1e-05 as a string, 1.0e-05 as a number.
    """
    style = '"' if isinstance(value, str) else None
    text = yaml.safe_dump(value, default_style=style, allow_unicode=True, width=_ONE_LINE)
    return text.removesuffix("\n").removesuffix("\n...")


# ---- the line editor ---------------------------------------------------------


class LayoutError(ValueError):
    """The file is valid YAML, but not laid out in a way the line editor handles."""


class _Line(NamedTuple):
    content: str
    ending: str  # "\n", "\r\n", or "" for a last line without one

    @property
    def indent(self) -> int:
        return len(self.content) - len(self.content.lstrip(" "))

    @property
    def is_content(self) -> bool:
        stripped = self.content.strip()
        return stripped != "" and not stripped.startswith("#")


def _split_lines(text: str) -> list[_Line]:
    parts = text.split("\n")
    lines = [
        _Line(part[:-1], "\r\n") if part.endswith("\r") else _Line(part, "\n")
        for part in parts[:-1]
    ]
    if parts[-1]:
        lines.append(_Line(parts[-1], ""))
    return lines


def edit_board(text: str, board_id: str, values: Mapping[str, str]) -> str:
    """text with the given keys of one board set to these YAML tokens.

    A key's value is replaced where it stands, keeping what follows it on the
    line, a comment included. A key the board lacks is added after its last
    line, indented like its other keys.
    """
    lines = _split_lines(text)
    start, end = _board_block(lines, board_id)
    keys_indent = next(line.indent for line in lines[start:end] if line.is_content)

    missing = dict(values)
    for index in range(start, end):
        line = lines[index]
        match = _KEY_LINE.fullmatch(line.content)
        if line.indent != keys_indent or match is None or match["key"] not in missing:
            continue
        following = next((other for other in lines[index + 1 : end] if other.is_content), None)
        if following is not None and following.indent > keys_indent:
            raise LayoutError(f"the value of {match['key']} spans several lines")
        token = missing.pop(match["key"])
        lines[index] = line._replace(content=_with_value(match, token))

    if missing:
        last = max(index for index in range(start, end) if lines[index].is_content)
        ending = lines[last].ending or next((line.ending for line in lines if line.ending), "\n")
        lines[last] = lines[last]._replace(ending=ending)
        added = [
            _Line(f"{' ' * keys_indent}{key}: {token}", ending) for key, token in missing.items()
        ]
        lines[last + 1 : last + 1] = added
    return "".join(line.content + line.ending for line in lines)


def _board_block(lines: list[_Line], board_id: str) -> tuple[int, int]:
    """The lines of one board's keys: from after its own line to before the next key."""
    boards_at = next(
        (
            index
            for index, line in enumerate(lines)
            if line.indent == 0 and re.fullmatch(r"boards:[ \t]*(#.*)?", line.content)
        ),
        None,
    )
    if boards_at is None:
        raise LayoutError("no 'boards:' line")

    board_indent = None
    for index in range(boards_at + 1, len(lines)):
        line = lines[index]
        if not line.is_content:
            continue
        if line.indent == 0:
            break
        board_indent = board_indent if board_indent is not None else line.indent
        match = _KEY_LINE.fullmatch(line.content)
        if line.indent != board_indent or match is None or match["key"] != board_id:
            continue
        if match["rest"].strip() and not match["rest"].strip().startswith("#"):
            raise LayoutError(f"board {board_id} is not written as a block of keys")
        end = index + 1
        while end < len(lines) and (not lines[end].is_content or lines[end].indent > line.indent):
            end += 1
        if not any(other.is_content for other in lines[index + 1 : end]):
            raise LayoutError(f"board {board_id} has no keys")
        return index + 1, end
    raise LayoutError(f"no line for board {board_id} under 'boards:'")


def _with_value(match: re.Match[str], token: str) -> str:
    """The key line with its value replaced by token, gap and comment kept."""
    rest = match["rest"]
    value_and_tail = rest.lstrip(" \t")
    gap = rest[: len(rest) - len(value_and_tail)] or " "
    tail = _tail(value_and_tail)
    if tail and not tail[0].isspace():
        tail = " " + tail  # a comment right after the colon needs a space before it
    return f"{match['indent']}{match['key']}:{gap}{token}{tail}"


def _tail(value_and_tail: str) -> str:
    """What follows the value on its line: spaces and a comment, or nothing."""
    text = value_and_tail
    if text == "" or text.startswith("#"):
        return text
    if text[0] == '"':
        end = _closing_quote(text, '"', escape="\\")
    elif text[0] == "'":
        end = _closing_quote(text, "'", escape="'")
    elif text[0] in "|>&*![{":
        raise LayoutError(f"cannot replace a value written as {text!r}")
    else:
        comment = re.search(r"[ \t]#", text)
        end = len(text.rstrip(" \t")) if comment is None else len(text[: comment.start()].rstrip())
    tail = text[end:]
    if tail.strip() and not re.match(r"[ \t]+#", tail):
        raise LayoutError(f"cannot replace a value written as {text!r}")
    return tail


def _closing_quote(text: str, quote: str, escape: str) -> int:
    """Index just past the quote that closes the string opening text."""
    index = 1
    while index < len(text):
        if text[index] == escape and escape != quote:
            index += 2
            continue
        if text[index] == quote:
            if escape == quote and text[index + 1 : index + 2] == quote:
                index += 2  # '' inside a single-quoted string
                continue
            return index + 1
        index += 1
    raise LayoutError("a quoted value continues on the next line")
