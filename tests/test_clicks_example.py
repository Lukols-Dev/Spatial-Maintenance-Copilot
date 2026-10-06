"""The clicks file is written by the web annotator and read by the atlas builder.

apps/web/lib/annotate/clicks.example.json is what the annotator's TypeScript
writes for a known set of clicks (its unit tests check that). Here the Python
side reads the same file, so a change of format on either side breaks a test.
"""

from pathlib import Path

from smc_core.contracts import load_clicks

EXAMPLE = Path(__file__).resolve().parents[1] / "apps/web/lib/annotate/clicks.example.json"


def test_the_annotator_example_is_a_clicks_file_the_atlas_builder_reads() -> None:
    clicks = load_clicks(EXAMPLE)

    assert clicks.camera_id == "phone-1x-portrait"
    assert clicks.points == ["corner_top_left", "drone"]
    assert set(clicks.views) == {"view_0.png", "view_1.png"}
    assert clicks.views["view_0.png"]["corner_top_left"] == (100.0, 200.0)
    assert clicks.views["view_0.png"]["drone"] == (299.75, 400.25)
    assert clicks.views["view_1.png"]["drone"] == (310.0, 410.0)
