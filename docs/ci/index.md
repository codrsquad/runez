# CI and code quality

CI is deliberately thin. `tox.ini` defines every check; the workflows in `.github/workflows/` only
set up a Python and a uv, then call `tox -e <something>`. That means anything CI does is
reproducible locally with the same one-liner, and adding a check is a tox edit rather than a
workflow edit.

Two workflows exist: one runs tests across the supported Python matrix plus the linters on every
push and PR, and one publishes to PyPI on a version tag using trusted publishing (no API token in
the repo). There is also a ripple-effect job that builds the downstream projects listed in
`ripple-effect.yml` against the PR's version of runez, to catch breakage before it lands.

Both pages below exist for the same reason: this pipeline has broken twice from *tooling that
updated itself*, not from anything committed to the repo. The policies are about making the build
depend only on what is checked in.

## Sections

- [GitHub Actions versions](./github-actions.md) — how actions are pinned, and why not to SHAs.
- [Code quality](./code-quality.md) — the linter and type-checker policies, and the pinning
  problem they only partly solve.
