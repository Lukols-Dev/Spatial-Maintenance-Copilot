"""Evaluate the localisation loop on a frozen dataset.

Writes eval/results/<dataset>/: results.json with every measure, report.md
with its tables, and traces/ with the agent's trace of every session. The
agent runs without a model unless --model is given: the policy's own words,
and no call to AWS. With --model it runs on the model of
services/perception/.env, as the service does.

A run with the model goes to its own folder, <dataset>-with-model: its
measures are the same, since the policy decides, but its traces hold the
model's words and how often the guards corrected them.

With --check nothing is written: the evaluation runs again and is compared
with the stored results.json within the tolerances of smc_eval.check. A model
does not answer the same twice, so a run with one is not checked.
"""

import argparse
import json
import logging
import platform
import subprocess
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import cv2 as cv
from smc_agent.contracts import TraceEvent
from smc_eval.check import differences
from smc_eval.dataset import DatasetError, load_dataset
from smc_eval.evaluate import NO_MODEL, evaluate
from smc_eval.perception import SAMPLES, SEED
from smc_eval.report import render
from smc_eval.results import Environment, Results

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"


def _git(root: Path, *args: str) -> str | None:
    found = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    return found.stdout.strip() if found.returncode == 0 else None


def environment(root: Path) -> Environment:
    status = _git(root, "status", "--porcelain")
    return Environment(
        git_commit=_git(root, "rev-parse", "HEAD") or None,
        git_dirty=None if status is None else bool(status),
        python=platform.python_version(),
        numpy=version("numpy"),
        opencv=cv.__version__,
        langgraph=version("langgraph"),
        machine=platform.machine(),
    )


def write(out: Path, results: Results, traces: dict[str, list[TraceEvent]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(results.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(render(results), encoding="utf-8")
    for relative, trace in traces.items():
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        events = [event.model_dump(mode="json") for event in trace]
        path.write_text(json.dumps(events, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="a frozen dataset folder")
    parser.add_argument("--out", type=Path, help="default: eval/results/<dataset name>")
    parser.add_argument("--root", type=Path, default=ROOT, help="the workspace")
    parser.add_argument("--samples", type=int, default=SAMPLES, help="Monte Carlo samples")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument(
        "--model", action="store_true", help="the agent's model of services/perception/.env"
    )
    parser.add_argument(
        "--check", action="store_true", help="compare with the stored results; write nothing"
    )
    args = parser.parse_args(argv)
    if args.check and args.model:
        parser.error("a run with the model is not checked: a model does not answer the same twice")

    try:
        dataset = load_dataset(args.dataset, args.root)
    except DatasetError as error:
        raise SystemExit(str(error)) from error
    out = args.out or RESULTS / (dataset.name + ("-with-model" if args.model else ""))

    model, model_name = None, NO_MODEL
    if not args.model:
        # Without a model every agent turn logs that it had none; the trace already says so.
        logging.getLogger("smc_agent.copilot").setLevel(logging.ERROR)
    else:
        # Only here: the evaluation without a model needs neither the service nor its keys.
        from smc_perception.agent import agent_model
        from smc_perception.agent import model_name as configured

        model, model_name = agent_model(), configured()

    results, traces = evaluate(
        dataset,
        evaluated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        environment=environment(args.root),
        samples=args.samples,
        seed=args.seed,
        model=model,
        model_name=model_name,
    )

    if args.check:
        stored = out / "results.json"
        if not stored.is_file():
            raise SystemExit(f"{stored} is missing: run the evaluation first")
        found = differences(
            json.loads(stored.read_text(encoding="utf-8")), results.model_dump(mode="json")
        )
        if found:
            raise SystemExit(f"{len(found)} results differ from {stored}:\n" + "\n".join(found))
        print(f"reproduced {stored} within the tolerances")
        return

    write(out, results, traces)
    localisation = results.localisation
    agent = next(strategy for strategy in results.strategies if strategy.strategy == "agent")
    print(f"written: {out}")
    print(
        f"  {localisation.localised} viewpoints localised with a truth: median error "
        f"{localisation.error_px.median:.1f} px, inside the 95% region "
        f"{localisation.inside_95.k}/{localisation.inside_95.n}"
        if localisation.error_px.median is not None
        else "  no viewpoint localised with a truth"
    )
    print(
        f"  agent sessions: {agent.success.k}/{agent.success.n} succeeded, "
        f"{agent.false_accept.k} false accepts"
    )


if __name__ == "__main__":
    main()
