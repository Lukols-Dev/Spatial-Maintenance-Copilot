import argparse
import os
import tempfile
from typing import Any, TypedDict

import cv2
import numpy as np
import numpy.typing as npt
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas


class BoardSpec(TypedDict):
    """One printed board, fully specified.

    A plain dict infers its value type as a union, so every read comes back as
    `str | int | float | list[int]` and arithmetic on it cannot be checked. The
    TypedDict gives each key its own type without changing a single call site.
    """

    name: str
    key: str
    squares_x: int
    squares_y: int
    square_mm: float
    marker_mm: float
    ids: list[int]
    dict_name: str


# Marker side as a fraction of the square side. 0.70 to 0.75 is the usual
# working range: large enough to decode at distance, small enough to leave a
# white quiet zone around each marker inside its square.
MARKER_RATIO = 0.72
DICT_NAME = "DICT_5X5_100"
DICT_BITS = 5

PX_PER_SQUARE = 720  # integer, keeps the raster grid commensurate with the print grid


def make_board(
    squares_x: int,
    squares_y: int,
    square_mm: float,
    marker_mm: float,
    dictionary: Any,
    ids: list[int],
) -> tuple[Any, npt.NDArray[Any]]:
    """Build a CharucoBoard object and render it to a numpy image."""
    board = cv2.aruco.CharucoBoard(
        (squares_x, squares_y),
        square_mm / 1000.0,  # OpenCV wants consistent units; metres here
        marker_mm / 1000.0,
        dictionary,
        np.array(ids, dtype=np.int32),
    )
    img = board.generateImage(
        (squares_x * PX_PER_SQUARE, squares_y * PX_PER_SQUARE),
        marginSize=0,
        borderBits=1,
    )
    return board, img


def draw_ruler(c: pdfcanvas.Canvas, x_mm: float, y_mm: float, length_mm: int = 100) -> None:
    """Draw a verification ruler with 10 mm ticks. If the printed ruler is not
    exactly length_mm long, the print scale was wrong and the board is unusable."""
    c.setLineWidth(0.4)
    c.setStrokeColorRGB(0, 0, 0)
    c.line(x_mm * mm, y_mm * mm, (x_mm + length_mm) * mm, y_mm * mm)
    for i in range(0, length_mm + 1, 10):
        tick = 3.5 if i % 50 == 0 else 2.0
        c.line((x_mm + i) * mm, y_mm * mm, (x_mm + i) * mm, (y_mm + tick) * mm)
    c.setFont("Helvetica", 6.5)
    c.drawString(x_mm * mm, (y_mm - 3.2) * mm, "0")
    c.drawRightString((x_mm + length_mm) * mm, (y_mm - 3.2) * mm, f"{length_mm} mm")


def draw_instructions_page(c: pdfcanvas.Canvas, specs: list[BoardSpec]) -> None:
    page_w_mm = A4[0] / mm
    page_h_mm = A4[1] / mm

    c.setFont("Helvetica-Bold", 13)
    c.drawString(18 * mm, (page_h_mm - 18) * mm, "ChArUco rig - print, verify, mount")
    c.setFont("Helvetica", 8)
    c.drawRightString(
        (page_w_mm - 18) * mm,
        (page_h_mm - 18) * mm,
        "PRINT AT 100% / ACTUAL SIZE - DO NOT FIT TO PAGE",
    )

    y = page_h_mm - 30
    c.setFont("Helvetica-Bold", 9)
    c.drawString(18 * mm, y * mm, "STEP 1  Confirm the print scale")
    c.setFont("Helvetica", 8.5)
    step1 = [
        "Print this page first. Measure the ruler below with a steel rule or calipers.",
        "It must read exactly 100.0 mm. If it reads 97 mm or 104 mm, the driver rescaled the page:",
        "set scaling to None / 100% / Actual size, turn off Fit to page and Shrink oversized pages, then reprint.",
        "Do not print the board pages until this ruler measures correctly.",
    ]
    for i, line in enumerate(step1):
        c.drawString(18 * mm, (y - 6 - i * 4.6) * mm, line)

    draw_ruler(c, 18.0, y - 6 - len(step1) * 4.6 - 6)

    y = y - 6 - len(step1) * 4.6 - 22
    c.setFont("Helvetica-Bold", 9)
    c.drawString(18 * mm, y * mm, "STEP 2  Print the boards")
    c.setFont("Helvetica", 8.5)
    step2 = [
        "Matte paper or matte adhesive vinyl only. Gloss produces specular highlights that destroy",
        "sub-pixel corner refinement under the workshop lighting the rig will actually face.",
        "Laser preferred over inkjet: crisper black-to-white transitions at the square boundary.",
        "Print in true black, greyscale off, toner saver off, no watermark or header from the driver.",
    ]
    for i, line in enumerate(step2):
        c.drawString(18 * mm, (y - 6 - i * 4.6) * mm, line)

    y = y - 6 - len(step2) * 4.6 - 8
    c.setFont("Helvetica-Bold", 9)
    c.drawString(18 * mm, y * mm, "STEP 3  Mount before measuring")
    c.setFont("Helvetica", 8.5)
    step3 = [
        "Bond each board to a rigid flat substrate: dibond, 2 to 3 mm aluminium, or 3 mm acrylic.",
        "Foamboard is acceptable short term, cardboard is not. Paper curl is a systematic pose error,",
        "not noise: it biases every observation in the same direction and will not average out.",
        "Apply adhesive over the full area, not at the corners, and roll out air bubbles.",
    ]
    for i, line in enumerate(step3):
        c.drawString(18 * mm, (y - 6 - i * 4.6) * mm, line)

    y = y - 6 - len(step3) * 4.6 - 8
    c.setFont("Helvetica-Bold", 9)
    c.drawString(18 * mm, y * mm, "STEP 4  Measure the mounted board and record the result")
    c.setFont("Helvetica", 8.5)
    step4 = [
        "Measure with calipers ACROSS FOUR SQUARES and divide by four. This divides your reading",
        "error by four and is the single cheapest accuracy gain available on this rig.",
        "Write the measured value into rig.yaml. Never use the nominal value from the generator:",
        "printers scale by a few tenths of a percent, and scale error propagates linearly into translation,",
        "so a 0.3% square error becomes a 0.3% range error and lands directly on the component position.",
        "Record the measurement uncertainty too. It is the input to the Monte Carlo uncertainty region.",
    ]
    for i, line in enumerate(step4):
        c.drawString(18 * mm, (y - 6 - i * 4.6) * mm, line)

    y = y - 6 - len(step4) * 4.6 - 8
    c.setFont("Helvetica-Bold", 9)
    c.drawString(
        18 * mm, y * mm, "ID ALLOCATION (disjoint ranges, no board can be confused with another)"
    )
    c.setFont("Helvetica", 8.5)
    rows = [("Board", "Layout", "IDs", "Square", "Extent")]
    for s in specs:
        rows.append(
            (
                s["key"],
                f"{s['squares_x']} x {s['squares_y']}",
                f"{s['ids'][0]}-{s['ids'][-1]}",
                f"{s['square_mm']:.1f} mm",
                f"{s['squares_x'] * s['square_mm']:.0f} x {s['squares_y'] * s['square_mm']:.0f} mm",
            )
        )
    cols = [18, 62, 96, 124, 156]
    for r, row in enumerate(rows):
        c.setFont("Helvetica-Bold" if r == 0 else "Helvetica", 8.5)
        for col, cell in zip(cols, row, strict=True):
            c.drawString(col * mm, (y - 6 - r * 4.8) * mm, cell)

    y = y - 6 - len(rows) * 4.8 - 8
    c.setFont("Helvetica", 8.5)
    c.drawString(
        18 * mm,
        y * mm,
        "Spare IDs 17-19, 32-34 and 47-99 are unallocated. Keep them free for later rig extensions.",
    )

    c.showPage()


def draw_page(c: pdfcanvas.Canvas, img_path: str, meta: BoardSpec) -> None:
    page_w_mm = A4[0] / mm
    page_h_mm = A4[1] / mm

    board_w_mm = meta["squares_x"] * meta["square_mm"]
    board_h_mm = meta["squares_y"] * meta["square_mm"]

    # Board is centred in the region between the header and the fixed footer.
    region_top_mm = 275.0
    region_bottom_mm = 60.0
    x0 = (page_w_mm - board_w_mm) / 2.0
    y0 = region_bottom_mm + (region_top_mm - region_bottom_mm - board_h_mm) / 2.0

    c.setFont("Helvetica-Bold", 11)
    c.drawString(18 * mm, (page_h_mm - 13) * mm, meta["name"])
    c.setFont("Helvetica", 8)
    c.drawRightString(
        (page_w_mm - 18) * mm,
        (page_h_mm - 13) * mm,
        "PRINT AT 100% / ACTUAL SIZE - DO NOT FIT TO PAGE",
    )

    # Board, placed at exact physical size
    c.drawImage(
        img_path,
        x0 * mm,
        y0 * mm,
        width=board_w_mm * mm,
        height=board_h_mm * mm,
        preserveAspectRatio=False,
        anchor="sw",
    )

    # Cut guide, kept 6 mm clear of the board so it never touches a marker
    c.setStrokeColorRGB(0.72, 0.72, 0.72)
    c.setLineWidth(0.3)
    c.rect(
        (x0 - 6) * mm,
        (y0 - 6) * mm,
        (board_w_mm + 12) * mm,
        (board_h_mm + 12) * mm,
        stroke=1,
        fill=0,
    )

    # Fixed footer: nominal specification in two columns
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(18 * mm, 52 * mm, "NOMINAL SPECIFICATION (not a measurement)")
    c.setFont("Helvetica", 8)
    left = [
        f"Dictionary: {meta['dict_name']}",
        f"Layout: ChArUco {meta['squares_x']} x {meta['squares_y']} squares",
        f"Marker IDs: {meta['ids'][0]} to {meta['ids'][-1]} ({len(meta['ids'])} markers)",
        f"rig.yaml key: {meta['key']}",
    ]
    right = [
        f"Square side: {meta['square_mm']:.2f} mm",
        f"Marker side: {meta['marker_mm']:.2f} mm",
        f"Board extent: {board_w_mm:.1f} x {board_h_mm:.1f} mm",
        f"Chessboard corners: {(meta['squares_x'] - 1) * (meta['squares_y'] - 1)}",
    ]
    for i, line in enumerate(left):
        c.drawString(18 * mm, (46 - i * 4.6) * mm, line)
    for i, line in enumerate(right):
        c.drawString(110 * mm, (46 - i * 4.6) * mm, line)

    draw_ruler(c, 18.0, 22.0)

    c.setFont("Helvetica", 8)
    c.drawString(
        18 * mm,
        14 * mm,
        "Measured square side: ................ mm      "
        "Uncertainty: +/- .......... mm      "
        "Date: ................",
    )

    c.showPage()


def _spec(
    name: str,
    key: str,
    squares_x: int,
    squares_y: int,
    square_mm: float,
    ids: list[int],
) -> BoardSpec:
    """Build one validated, complete board specification.

    The ID count is checked here rather than by the caller, so a spec object
    cannot exist in an invalid state. The marker side is derived, not supplied:
    the clearance rule between square and marker depends on the ratio, and
    letting a caller set both independently is how that rule gets broken.
    """
    expected = (squares_x * squares_y) // 2
    if len(ids) != expected:
        raise ValueError(f"{name}: {len(ids)} IDs supplied, board needs {expected}")
    return BoardSpec(
        name=name,
        key=key,
        squares_x=squares_x,
        squares_y=squares_y,
        square_mm=square_mm,
        marker_mm=round(square_mm * MARKER_RATIO, 2),
        ids=ids,
        dict_name=DICT_NAME,
    )


def board_specs(calib_square: float = 30.0, rig_square: float = 25.0) -> list[BoardSpec]:
    """The rig definition: one entry per printed board.

    The single source of truth for dictionary, layout and ID ranges. The
    generator draws from it and the tests verify it, so a test cannot pass
    against parameters that differ from the ones sent to the printer.
    """
    return [
        _spec(
            "Calibration board - ChArUco 5x7",
            "calibration_board",
            5,
            7,
            calib_square,
            list(range(0, 17)),
        ),
        _spec("Rig board A - ChArUco 4x6", "rig_board_a", 4, 6, rig_square, list(range(20, 32))),
        _spec("Rig board B - ChArUco 4x6", "rig_board_b", 4, 6, rig_square, list(range(35, 47))),
    ]


def get_dictionary() -> Any:
    """The single dictionary used by every board in this rig."""
    return cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, DICT_NAME))


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate print-exact ChArUco boards.")
    ap.add_argument(
        "--calib-square",
        type=float,
        default=30.0,
        help="calibration board square side in mm (default 30)",
    )
    ap.add_argument(
        "--rig-square", type=float, default=25.0, help="rig board square side in mm (default 25)"
    )
    ap.add_argument("--out", default="charuco_boards_A4.pdf", help="output PDF path")
    ap.add_argument("--yaml", default="rig_nominal.yaml", help="output YAML stub path")
    args = ap.parse_args()

    dict_name = DICT_NAME
    dictionary = get_dictionary()

    specs = board_specs(args.calib_square, args.rig_square)

    tmpdir = tempfile.mkdtemp()
    c = pdfcanvas.Canvas(args.out, pagesize=A4)
    c.setTitle("ChArUco boards - Spatial Maintenance Copilot rig")

    draw_instructions_page(c, specs)

    for spec in specs:
        _, img = make_board(
            spec["squares_x"],
            spec["squares_y"],
            spec["square_mm"],
            spec["marker_mm"],
            dictionary,
            spec["ids"],
        )
        img_path = os.path.join(tmpdir, spec["key"] + ".png")
        cv2.imwrite(img_path, img)
        draw_page(c, img_path, spec)

    c.save()

    with open(args.yaml, "w") as f:
        f.write("# Nominal geometry emitted by gen_charuco_boards.py.\n")
        f.write("# Replace every *_measured_mm value with a caliper reading from the\n")
        f.write("# printed and mounted board before any pose is computed.\n")
        f.write(f"dictionary: {dict_name}\n")
        f.write(f"marker_ratio: {MARKER_RATIO}\n")
        f.write("boards:\n")
        for spec in specs:
            f.write(f"  {spec['key']}:\n")
            f.write(f"    squares_x: {spec['squares_x']}\n")
            f.write(f"    squares_y: {spec['squares_y']}\n")
            f.write(f"    ids: [{spec['ids'][0]}, {spec['ids'][-1]}]  # inclusive range\n")
            f.write(f"    square_nominal_mm: {spec['square_mm']}\n")
            f.write(f"    marker_nominal_mm: {spec['marker_mm']}\n")
            f.write("    square_measured_mm: null\n")
            f.write("    marker_measured_mm: null\n")
            f.write("    measurement_uncertainty_mm: null\n")
            f.write("    substrate: null\n")
            f.write("    measured_on: null\n")

    print(f"PDF:  {args.out}")
    print(f"YAML: {args.yaml}")
    for spec in specs:
        print(
            f"  {spec['key']}: {spec['squares_x'] * spec['square_mm']:.1f} x "
            f"{spec['squares_y'] * spec['square_mm']:.1f} mm, "
            f"square {spec['square_mm']} mm, marker {spec['marker_mm']} mm, "
            f"IDs {spec['ids'][0]}-{spec['ids'][-1]}"
        )


if __name__ == "__main__":
    main()
