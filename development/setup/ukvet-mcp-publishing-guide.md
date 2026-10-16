# Publishing `ukvet-mcp` to TestPyPI and PyPI

This guide explains how the `release-mcp.yml` GitHub Actions workflow builds and publishes the `ukvet-mcp` package.

## Overview

The workflow is located at:

```text
.github/workflows/release-mcp.yml
```

It builds the package, runs tests, and publishes the built distribution to either TestPyPI or production PyPI. The destination depends on how the workflow is triggered.

## What the workflow does

The `build` job:

1. Checks out the repository.
2. Sets up Python and `uv`.
3. Installs the development dependencies.
4. Runs the test suite.
5. Checks that a release tag matches the package version when triggered by a tag.
6. Builds `ukvet-mcp` into distribution files under `dist/`.
7. Uploads `dist/` as a GitHub Actions artifact.

The selected publish job downloads that artifact and uploads it. The publish job does not rebuild the package within that run.

## How to publish

### 1. Push code changes

Make your changes and push them to `main` as usual. A normal push to `main` does **not** trigger this release workflow.

The package version is defined in:

```text
packages/ukvet-mcp/pyproject.toml
```

Before publishing, make sure the version is correct and has not already been uploaded to the destination index.

### 2. Publish a test release to TestPyPI

Use this when you want to check that the package can be installed from a package index before making a production release.

1. Open the repository on GitHub.
2. Go to **Actions**.
3. Select **Release ukvet-mcp**.
4. Click **Run workflow**.
5. Select branch `main`.
6. Choose `testpypi` as the target.
7. Start the workflow and wait for it to finish successfully.
8. Check the package page: <https://test.pypi.org/project/ukvet-mcp/>.

The workflow builds the package and uploads it to **TestPyPI only**.

For an installation check in Windows PowerShell, use a fresh virtual environment and the following commands (run them separately):

```powershell
uv venv
uv pip install --python .venv\Scripts\python.exe --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ ukvet-mcp
```

The TestPyPI index is checked first. The extra index allows dependencies that are not published on TestPyPI to be found on production PyPI.

### 3. Publish a production release to PyPI

Only do this when you are ready to make the release publicly available.

First, confirm that:

- the code and README changes have been committed and pushed;
- `packages/ukvet-mcp/pyproject.toml` contains the intended version;
- the version has not already been published to production PyPI;
- the production PyPI Trusted Publisher is configured for repository `FraidoonOmarzai/ukvet`, workflow `release-mcp.yml`, and GitHub environment `pypi`.

For example, if the package version is `0.1.1`, run these commands from the repository root in PowerShell:

```powershell
git tag ukvet-mcp-v0.1.1
git push origin ukvet-mcp-v0.1.1
```

Replace `0.1.1` with the actual version in `pyproject.toml`.

Pushing a tag matching `ukvet-mcp-v*` automatically triggers the workflow's production PyPI job. The build and tests run first; if they pass, the package is uploaded to **production PyPI**.

Verify the release at <https://pypi.org/project/ukvet-mcp/>.

**Important:** do not push a release tag until you are ready to publish publicly. With the current workflow, a matching tag triggers production publishing automatically.

## Current workflow: important distinction

The current workflow does **not** publish to TestPyPI and then automatically promote that same artifact to PyPI.

Instead, TestPyPI and PyPI are separate workflow runs:

| Trigger | Destination |
|---|---|
| Push a normal commit to `main` | No release workflow run |
| Manually run the workflow with target `testpypi` | TestPyPI |
| Manually run the workflow with target `pypi` | Production PyPI |
| Push a matching tag such as `ukvet-mcp-v0.1.1` | Production PyPI |

Each run has its own build job. Therefore, the TestPyPI build and the production PyPI build are separate builds, even if they use the same source version. The build artifact is reused between the build and publish jobs **within a single workflow run**, but not automatically between separate TestPyPI and PyPI runs.

If you need a strict “build once, test that exact artifact, then promote that exact artifact” process, the workflow must be redesigned to retain and promote the same artifact across the test and production stages.

## Version numbers and re-uploads

Package indexes generally do not allow you to overwrite an existing uploaded release file with a different file. TestPyPI and production PyPI are separate indexes, so a version may exist on both, but avoid trying to upload a different build using a version already used on the same index.

For example, if version `0.1.1` has already been uploaded to TestPyPI and you need to change the package contents, increment the version before uploading the changed build to TestPyPI again.

A release-candidate version such as `0.1.2rc1` can be useful for pre-release testing, followed by the final version `0.1.2` for production. Ensure the project metadata, package version constant (if your project maintains one), and release tag all agree.

## Trusted Publishing (OIDC)

This workflow uses PyPI Trusted Publishing rather than a stored API token. Configure publishers separately on TestPyPI and production PyPI.

The expected GitHub repository is `FraidoonOmarzai/ukvet`, and the workflow filename is `release-mcp.yml`.

- TestPyPI publish job: GitHub environment `testpypi`.
- Production PyPI publish job: GitHub environment `pypi`.

The corresponding Trusted Publisher configuration must match the repository owner, repository name, workflow filename, and environment exactly. The publish jobs need `permissions: id-token: write` for OIDC authentication.

## Quick release checklist

- [ ] Update and review the code and README.
- [ ] Update the package version in `packages/ukvet-mcp/pyproject.toml` when making a new release.
- [ ] Commit and push changes to `main`.
- [ ] Run the workflow manually with target `testpypi`.
- [ ] Install and verify the TestPyPI package.
- [ ] Confirm the production version is unused and the production publisher is configured.
- [ ] Push a matching version tag only when ready for public release.
- [ ] Confirm the GitHub Actions run succeeds.
- [ ] Verify the new version on <https://pypi.org/project/ukvet-mcp/>.
