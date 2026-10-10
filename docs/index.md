# runez internal docs

These are the *inside view* docs for the runez repo: how it is built, tested and released, and the
"why" behind choices that aren't obvious from reading the code. They are for people (and coding
agents) working **on** runez. Users of the library want the [README](../README.rst) and the
docstrings instead.

runez is a zero-dependency convenience library for Python 3.10+. Everything ships from
`src/runez/`, one module per concern (`file`, `program`, `pyenv`, `logsetup`, `render`, ...), all
re-exported from `src/runez/__init__.py` — that file is the public API surface and the best place
to start reading. Tests mirror the modules one-for-one under `tests/`.

`tox.ini` is the hub: every check a developer or CI can run is a tox environment, and the GitHub
workflows do nothing but call into them. If you want to know what CI actually does, read `tox.ini`
first and `.github/workflows/` second.

## Sections

- [Contributing](./contributing.md) — get a local venv going, run the tests, read coverage.
- [CI and code quality](./ci/index.md) — how the pipeline is wired, and the tool-version, linter
  and type-checker policies.
- [Type checker findings](./typecheck-findings.md) — what introducing multiple CI type checkers
  found and fixed.
- [Async cached_property](./async-cached-property.md) — a parked design: an async-capable
  `@runez.cached_property` that was written and tested but deliberately not shipped.
- [History](./history.rst) — the changelog.
