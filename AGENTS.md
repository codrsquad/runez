# AGENTS.md

runez is a zero-dependency convenience library for Python 3.10+. The repo docs live in
[`docs/`](./docs/index.md) — read them rather than re-deriving how this repo works.

## Looking for

- **How to use runez** → [`README.rst`](./README.rst) and the docstrings. `docs/` is *internal*,
  not published anywhere; users never see it.
- **How to develop on it** → [`docs/contributing.md`](./docs/contributing.md) — venv, tests,
  coverage.
- **How CI is wired, and the tooling policies** → [`docs/ci/index.md`](./docs/ci/index.md).
  Notably: ruff uses `select` (never `extend-select`), and actions are pinned to tags, not SHAs —
  both have a written rationale, so don't "fix" them without reading it.
- **What changed** → [`docs/history.rst`](./docs/history.rst).

## Working notes

- `tox.ini` is the hub. Every check is a tox environment and the workflows just call them, so
  reproduce any CI failure locally with the same `tox -e <env>`.
- Run tests with `.venv/bin/pytest` or through tox. Driving pytest from an unrelated interpreter
  breaks runez's own `sys.argv` canonicalization and produces confusing failures.
- `src/runez/__init__.py` is the public API surface, and `tests/extra-validations` enforces that
  its imports and `__all__` stay in the same order — add exports in both places.
- runez ships `py.typed`, so annotations are part of the contract. Prefer fixing a signature over
  adding an ignore comment.
- Each type checker has a tox env named after it (`tox -e ty`, `tox -e pyright`, ...); `ty` is the
  one being driven to zero, `src/` first. No `# type: ignore` / `# ty: ignore` markers, ever — see
  [`docs/typecheckers/`](./docs/typecheckers/index.md).
