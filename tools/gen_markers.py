"""Generate the printable ArUco markers: the cabinet's landmarks and the target's tag.

One A4 page, printed at 100%: twelve 40 mm markers of the rig's dictionary,
each in a white quiet zone inside a cut line, and a ruler to check the scale.
IDs 50 to 60 are landmarks, stuck on the cabinet; ID 70 is the target's tag,
stuck on the box. None of them is a marker of a board from
gen_charuco_boards.py, so a frame that shows both is read without confusion.

Their positions are not set here: the atlas triangulates every marker corner
from the views of the rig board, as it did the hand-marked crosses.
"""

import argparse
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy.typing as npt
from gen_charuco_boards import DICT_NAME, draw_ruler, get_dictionary
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas

MARKER_MM = 40.0  # the black square, its border included
# White around the marker: a decoder needs at least one module of it, and a
# 5x5 marker with its border is 7 modules across.
QUIET_MM = 8.0
LANDMARK_IDS = list(range(50, 61))
TARGET_ID = 70
PX_PER_MARKER = 700  # a multiple of the 7 modules, so every module is a whole number of pixels

COLUMNS, ROWS = 3, 4
CELL_W_MM = MARKER_MM + 2 * QUIET_MM
CELL_H_MM = CELL_W_MM + 8.0  # room for the ID under the cut line
GRID_TOP_MM = 279.0
LABEL_BELOW_MM = 4.5  # the ID's baseline under the cut line
FOOTER_TOP_MM = 25.0  # the footer's text and ruler stay below this


def marker_ids() -> list[int]:
    return [*LANDMARK_IDS, TARGET_ID]


def render_marker(dictionary: Any, marker_id: int, px: int = PX_PER_MARKER) -> npt.NDArray[Any]:
    return cv2.aruco.generateImageMarker(dictionary, marker_id, px, borderBits=1)


def label(marker_id: int) -> str:
    return f"ID {marker_id} - target (box)" if marker_id == TARGET_ID else f"ID {marker_id}"


def cell_origin(index: int) -> tuple[float, float]:
    """The lower-left corner of a cell's cut line, in mm from the page's lower-left corner."""
    page_w_mm = A4[0] / mm
    left = (page_w_mm - COLUMNS * CELL_W_MM) / 2.0
    row, column = divmod(index, COLUMNS)
    return left + column * CELL_W_MM, GRID_TOP_MM - (row + 1) * CELL_H_MM + 8.0


def draw_sheet(c: pdfcanvas.Canvas, images: dict[int, str]) -> None:
    page_w_mm = A4[0] / mm
    page_h_mm = A4[1] / mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, (page_h_mm - 11) * mm, "ArUco landmarks - Spatial Maintenance Copilot")
    c.setFont("Helvetica", 8)
    c.drawRightString(
        (page_w_mm - 18) * mm,
        (page_h_mm - 11) * mm,
        "PRINT AT 100% / ACTUAL SIZE - DO NOT FIT TO PAGE",
    )

    for index, marker_id in enumerate(marker_ids()):
        x, y = cell_origin(index)
        c.setStrokeColorRGB(0.72, 0.72, 0.72)
        c.setLineWidth(0.3)
        c.setDash(2, 2)
        c.rect(x * mm, y * mm, CELL_W_MM * mm, CELL_W_MM * mm, stroke=1, fill=0)
        c.setDash()
        c.drawImage(
            images[marker_id],
            (x + QUIET_MM) * mm,
            (y + QUIET_MM) * mm,
            width=MARKER_MM * mm,
            height=MARKER_MM * mm,
            preserveAspectRatio=False,
            anchor="sw",
        )
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 8)
        c.drawCentredString((x + CELL_W_MM / 2) * mm, (y - LABEL_BELOW_MM) * mm, label(marker_id))

    c.setFont("Helvetica", 7.5)
    c.drawString(
        18 * mm,
        (FOOTER_TOP_MM - 3) * mm,
        f"{DICT_NAME}, marker side {MARKER_MM:.1f} mm with its border. "
        "Cut on the dashed line, keep the white margin.   Measured side: .......... mm",
    )
    draw_ruler(c, 18.0, 12.0)
    c.showPage()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("markers_A4.pdf"), help="the PDF to write")
    args = parser.parse_args(argv)

    dictionary = get_dictionary()
    folder = Path(tempfile.mkdtemp())
    images = {}
    for marker_id in marker_ids():
        path = folder / f"marker_{marker_id}.png"
        cv2.imwrite(str(path), render_marker(dictionary, marker_id))
        images[marker_id] = str(path)

    c = pdfcanvas.Canvas(str(args.out), pagesize=A4)
    c.setTitle("ArUco landmarks - Spatial Maintenance Copilot")
    draw_sheet(c, images)
    c.save()
    print(f"saved: {args.out}")


if __name__ == "__main__":
    main()
