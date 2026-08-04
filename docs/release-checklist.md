# Release checklist

Use this checklist before tagging a ContractMesh release.

> **Audience:** ContractMesh maintainers. This is not a workspace setup guide.

## Version and release notes

- Confirm `VERSION` and `pyproject.toml` match.
- Update `RELEASE_NOTES.md`.

## Build and validate

- Build and validate artifacts:
  - `python3 -m pip install build twine`
  - `rm -rf dist/ build/ *.egg-info`
  - `python3 -m build`
  - `python3 -m twine check dist/*`
- Run the full release gate **from source checkout** (editable install or venv):
  - `contractmesh check --release`
- Validate the **pipx wheel install** (end-user path):
  - `pipx uninstall contractmesh`
  - `pipx install "$(ls dist/contractmesh-*-py3-none-any.whl)"`
  - `pipx inject contractmesh "mcp>=1.2.0,<2"` (if the `[mcp]` extra on the local wheel is unavailable)
  - `~/.local/bin/contractmesh self check`
  - `contractmesh check` in a temp project (`init --here`, `index`, `check`)
- Run individual checks when debugging failures:
  - `python3 -m unittest scripts.lib.test_fetch_hits`
  - `python3 -m unittest scripts.lib.test_preflight_change`
  - `bash scripts/test-mcp-workspace-knowledge.sh`
  - `bash scripts/test-preflight-smoke.sh`
- Run CLI smoke checks:
  - `contractmesh --help`
  - `contractmesh self check`
  - `contractmesh graph` (with `CONTRACTMESH_WORKSPACE` pointing at fixture)

## Documentation and security

- Confirm `.contractmeshignore` excludes project-specific sensitive paths.
- Confirm the fixture impact question works:
  - `What changes if ExampleService greeting rules change?`
- Review `README.md`.
- Review `docs/mcp-clients.md`.
- Review `docs/security-privacy.md`.
- Ensure generated files under `.contractmesh/` are not committed.
- Search for obsolete public-surface references such as `docs/generated`,
  `scripts/repos.conf`, `templates/demo`, and `contractmesh demo`; historical
  mentions in `RELEASE_NOTES.md` are expected.

## Publish

- Create a signed or annotated tag matching `VERSION`, for example:
  - `git tag -a "v$(tr -d '[:space:]' < VERSION)" -m "ContractMesh v$(tr -d '[:space:]' < VERSION)"`
- Create a GitHub Release for that tag. `.github/workflows/publish.yml` builds
  the wheel/sdist and uploads to PyPI via Trusted Publishing (OIDC).
- One-time: configure the pending trusted publisher on PyPI for owner
  `fabiodepin`, project `contractmesh`, workflow `publish.yml`, environment
  `pypi`, and create the matching GitHub Environment.
- After publish, verify:
  - `pipx install "contractmesh[mcp]"`
  - `contractmesh --help`
  - `contractmesh self check`
