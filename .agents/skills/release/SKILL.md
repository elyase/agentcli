---
name: release
description: Prepare and ship an agentcli release. Use when asked to cut a release, bump release versions, tag v<major.minor.patch>, or trigger the GitHub release workflow.
---

# Release

## Overview

Prepare a tagged release that matches the GitHub Actions release workflow. The workflow requires the tag version to match both `pyproject.toml` and `src/humancli/__init__.py`.

## Workflow

### 1) Choose version + date

Pick the release version (major.minor.patch) and the release date (YYYY-MM-DD).
If the current version has a `.dev` suffix, assume the target release version is the same version without the suffix, as long as that tag does not already exist.

### 2) Bump versions

Update version strings to match the release tag:

- `pyproject.toml`: `project.version = "<major.minor.patch>"`
- `src/humancli/__init__.py`: `__version__ = "<major.minor.patch>"`
- `uv.lock`: refresh so the root package version matches (run `uv lock` or `uv sync`).

### 3) Run checks

Run tests before committing:

- `uv run python -m unittest tests/test_agentcli.py`

### 4) Commit + tag

Commit the release using conventional commits:

- Commit message: `chore(release): v<major.minor.patch>`
- Tag: `git tag v<major.minor.patch>`

Push the tag to trigger `.github/workflows/release.yml` (build, PyPI publish, GitHub release).

### 5) Optional post-release bump

If you keep a dev version between releases, bump the minor version (reset patch to 0) and commit (`chore: bump version to ...`).

## Notes

- The release workflow checks that the tag matches `pyproject.toml` and `src/humancli/__init__.py`.
