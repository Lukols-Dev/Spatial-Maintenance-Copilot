"""tools/freeze_dataset.py and tools/evaluate.py, run as a user runs them, on the synthetic workspace."""

import json
import re
from pathlib import Path

import evaluate as evaluate_tool
import freeze_dataset
import pytest
from eval_scene import TEST, write_workspace


def freeze_arguments(root: Path, paths: dict[str, Path]) -> list[str]:
    return [
        "cabinet-test",
        "--atlas",
        str(paths["atlas"]),
        "--test",
        str(paths["test"]),
        "--build",
        str(paths["build"]),
        "--videos",
        str(paths["videos"]),
        "--intrinsics",
        str(root / "calib" / "intrinsics"),
        "--rig",
        str(root / "calib" / "rig.yaml"),
        "--root",
        str(root),
        "--out",
        str(root / "eval" / "datasets"),
    ]


def freeze(root: Path) -> Path:
    freeze_dataset.main(freeze_arguments(root, write_workspace(root)))
    return root / "eval" / "datasets" / "cabinet-test"


def verify(root: Path) -> None:
    freeze_dataset.main(
        ["cabinet-test", "--verify", "--root", str(root), "--out", str(root / "eval" / "datasets")]
    )


def test_a_dataset_is_frozen_and_its_media_verified(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = freeze(tmp_path)

    assert (folder / "manifest.json").is_file()
    printed = capsys.readouterr().out
    assert "atlas home-cabinet v1, camera phone-1x-portrait" in printed
    assert f"test set {TEST}: 7 frames" in printed

    verify(tmp_path)
    assert "every source file is there, unchanged" in capsys.readouterr().out

    (tmp_path / "data" / "recordings" / "B" / "B1_close.MOV").unlink()
    with pytest.raises(SystemExit, match=re.escape("B1_close.MOV is missing")):
        verify(tmp_path)


def test_a_camera_no_intrinsics_describe_cannot_be_frozen(tmp_path: Path) -> None:
    paths = write_workspace(tmp_path)
    paths["camera"].unlink()

    with pytest.raises(SystemExit, match="no intrinsics for phone-1x-portrait"):
        freeze_dataset.main(freeze_arguments(tmp_path, paths))


def test_the_evaluation_writes_its_results_and_reproduces_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = freeze(tmp_path)
    out = tmp_path / "eval" / "results" / "cabinet-test"
    arguments = [str(folder), "--root", str(tmp_path), "--out", str(out), "--samples", "100"]

    evaluate_tool.main(arguments)

    assert sorted(path.name for path in out.iterdir()) == ["report.md", "results.json", "traces"]
    assert len(list((out / "traces" / TEST).glob("*.json"))) == 4
    stored = json.loads((out / "results.json").read_text())
    assert stored["model"] == "none" and stored["environment"]["git_commit"] is None
    assert "2 viewpoints localised with a truth" in capsys.readouterr().out

    evaluate_tool.main([*arguments, "--check"])
    assert "reproduced" in capsys.readouterr().out

    stored["localisation"]["inside_95"]["k"] = 1
    (out / "results.json").write_text(json.dumps(stored))
    with pytest.raises(SystemExit, match=re.escape("localisation.inside_95.k: 1, now 2")):
        evaluate_tool.main([*arguments, "--check"])


def test_a_dataset_changed_after_its_freeze_is_not_evaluated(tmp_path: Path) -> None:
    folder = freeze(tmp_path)
    (folder / "atlas.json").write_text("{}")

    with pytest.raises(SystemExit, match=re.escape("atlas.json has changed")):
        evaluate_tool.main([str(folder), "--root", str(tmp_path)])


def test_a_run_with_the_model_is_never_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        evaluate_tool.main([str(tmp_path), "--model", "--check"])

    assert "a run with the model is not checked" in capsys.readouterr().err
