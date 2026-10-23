# Spatial Maintenance Copilot

> An Agentic Vision system for spatial guidance during equipment inspection and maintenance.

Spatial Maintenance Copilot was built for the **OpenCV AI Competition 2026, powered by AWS**, on the
Agentic Vision path.

The project was selected as one of **55 recipients of an AWS Compute Grant** during the competition build phase.

| | |
|---|---|
| Live application | <https://d14b6iicnc69ik.cloudfront.net> (AWS eu-north-1) |
| Technical report | [docs/report.md](docs/report.md), also as [PDF](docs/report.pdf) |
| Diagrams | [architecture](docs/architecture.png), [agent workflow](docs/agent-workflow.png) |
| Evaluation | [eval/results/cabinet-aruco-2026-10-23/report.md](eval/results/cabinet-aruco-2026-10-23/report.md) |

## Try it

The live application needs neither the cabinet nor a calibrated phone:

- **Demo**: act as the operator on recorded viewpoints. Every landmark, quality check, decision and agent
  turn is shown, with the session's trace.
- **Localise → Recording**: play one of four phone recordings through the loop the phone runs live: the
  overlay, the policy's move, the agent's words and, once the flap opens, the target's tag checked against
  the prediction.
- **Atlas**: the Component Atlas, its landmarks and view sets.

## About

Maintenance documentation can explain where a component is generally located, but this does not necessarily tell a user where that component is relative to the physical object currently in front of them.

Spatial Maintenance Copilot explores how:

- computer vision,
- spatial reasoning,
- measured localisation quality,
- and AI agents

can work together to provide spatial guidance during inspection and maintenance tasks.

The project focuses on situations where the target component may be difficult or impossible to see directly.

## Technology

- **OpenCV 5** (`opencv-python-headless` 5.0.0.93): ArUco and ChArUco detection, camera calibration,
  `solvePnPRansac` and `solvePnPRefineLM`, Monte Carlo uncertainty, marker-based blur measurement
- **The agent**: a LangGraph loop with typed tools, guards and a trace; Amazon Nova 2 Lite on Amazon Bedrock
- **Service and web app**: Python 3.14 with FastAPI, and a static Next.js app
- **AWS**: CloudFront, S3, API Gateway, ECS Fargate on Graviton, DynamoDB, Bedrock and CloudWatch, as an
  AWS CDK app

## Repository layout

```
apps/web/              Next.js static frontend (S3 + CloudFront)
packages/smc_core/     Geometry: calibration, atlas, PnP, Monte Carlo region, decision policy
packages/smc_agent/    The agent: a LangGraph loop over smc_core, Amazon Nova or Claude on Amazon Bedrock
packages/smc_eval/     The evaluation: metrics, a simulated operator, injected faults
services/perception/   FastAPI service running the pipeline and the agent (ECS Fargate)
infra/                 The AWS deployment as an AWS CDK app
eval/datasets/         Frozen evaluation datasets: atlas, clicks, board poses, media hashes
eval/results/          Evaluation results, report and agent traces
tools/                 Bench utilities and git hooks
docs/                  The technical report
```

Single uv workspace. The geometry lives in smc_core and the agent in smc_agent;
the service reads and writes files and calls them, never computing in the HTTP
layer.

## Running locally

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 20.9+, Docker.

```bash
make setup     # install the workspace and git hooks
cp services/perception/.env.example services/perception/.env   # the service's settings and keys
cp apps/web/.env.example apps/web/.env.local                    # the web app's API address
make api       # perception service on :8000
make web       # frontend on :3000
make check     # lint, type check, tests
```

Run `make help` for the full list of targets.

The containerised service, which is what gets deployed:

```bash
make api-build
make api-run
```

## Deploying to AWS

The stack in [infra/](infra/) (AWS CDK, region eu-north-1) puts the web app on S3 and CloudFront. The
API is served under `/api` through API Gateway, a VPC link and an internal load balancer, to the
service on ECS Fargate (Graviton). Agent sessions are kept in DynamoDB, and the workspace the demo
serves sits in a private S3 bucket. The task role signs Bedrock calls, so no key is stored in AWS.

Requirements: AWS credentials allowed to deploy, Docker, and access to Amazon Nova 2 Lite in
eu-north-1.

```bash
cd infra && npx cdk bootstrap   # once per account and region
make deploy                     # builds the web app for /api, the ARM64 image, and deploys
```

`infra/cdk.json` names the atlases and view sets of `data/` that the deployment serves. The stack's
outputs give the site's URL, the bucket, the sessions table and the service's log group.

## Evaluation

The evaluation runs the service's code on a frozen dataset. The atlas is scored on viewpoints recorded
apart from the views it was built from, with the target hidden. The truth is the target clicked in the
shot taken from the same spot with the target in sight.

It measures:

- localisation error, reprojection error and RANSAC inliers;
- pose stability, against repeated shots and the rig board;
- calibration of the 95% region, and the policy's decisions against the truth;
- task success and the agent's next view, against a single view, the policy alone and a random view;
- injected faults: missing landmarks, swapped labels, a gross click error, click noise.

The main result is the marker dataset of 2026-10-23, 27 tripod viewpoints with the box hidden
([report](eval/results/cabinet-aruco-2026-10-23/report.md)):
- a median target error of 1.7 px;
- the truth inside the 95% region in 22 of 22;
- no wrong result accepted;
- 25 of 25 agent sessions successful.

The same run with Amazon Nova as the agent's model is in
[cabinet-aruco-2026-10-23-with-model](eval/results/cabinet-aruco-2026-10-23-with-model/report.md). The
clicked baseline is [cabinet-manual-2026-10-09](eval/results/cabinet-manual-2026-10-09/report.md).

```bash
make eval        # run it: results.json, report.md and the agent's traces
make eval-check  # run it again and compare with the stored results, within fixed tolerances
make eval EVAL_DATASET=eval/datasets/cabinet-manual-2026-10-09   # another frozen dataset
```

## Documentation

[docs/report.md](docs/report.md) ([PDF](docs/report.pdf)) is the technical report. It covers:
- the problem and its users;
- the architecture and the agent's workflow;
- the OpenCV 5 implementation and the AWS deployment;
- the evaluation with its failure cases;
- the changes from the proposal, the limitations and responsible use.

## OpenCV AI Competition 2026

Primary track: **Agentic Vision**

Solo project by **Łukasz Olszewski**

#OpenCVComp26

## License

Apache License 2.0. See [LICENSE](LICENSE).
