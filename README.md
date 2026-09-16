# Spatial Maintenance Copilot

> An Agentic Vision system for spatial guidance during equipment inspection and maintenance.

🚧 **Status: Active development**

Spatial Maintenance Copilot is being developed for the **OpenCV AI Competition 2026, powered by AWS**.

The project was selected as one of **55 recipients of an AWS Compute Grant** during the competition build phase.

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

Currently exploring:

- OpenCV 5
- Python
- Computer Vision
- Multimodal AI
- AI Agents
- AWS

## Repository layout

```
apps/web/              Next.js static frontend (S3 + CloudFront)
services/perception/   FastAPI service running the OpenCV pipeline (ECS Fargate)
tools/                 Bench utilities and git hooks
```

Single uv workspace. Geometry will live in a standalone library imported by the
service, never computed in the HTTP layer.

## Running locally

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 20.9+, Docker.

```bash
make setup     # install the workspace and git hooks
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

## Current stage

The project is currently in the experimentation and prototyping phase.

The first goal is to validate the underlying computer-vision and spatial-localisation approach before expanding the system.

Technical details, experiments and demos will be published progressively as individual parts of the system are validated.

## OpenCV AI Competition 2026

Primary track: **Agentic Vision**

Solo project by **Łukasz Olszewski**

#OpenCVComp26

## License

Apache License 2.0. See [LICENSE](LICENSE).
