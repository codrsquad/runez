# Contributing

Contributions are welcome. [tox](https://github.com/tox-dev/tox) drives building and testing, and
`setup.py` stays trivial thanks to [setupmeta](https://pypi.org/project/setupmeta/).

## Get going locally

```shell
git clone https://github.com/codrsquad/runez.git  # or your own fork
cd runez

uv venv
uv pip install -r tests/requirements.txt -e .

# You have a venv now in ./.venv, use it, open it with pycharm etc
.venv/bin/python -mrunez colors
```

Activate it if you prefer working that way:

```shell
source .venv/bin/activate
python
>>> import runez
>>> runez.which("python")
```

Dependencies come from `tests/requirements.txt` and tox; this repo is not managed as a uv project,
so there is no `uv sync` step. A `uv.lock` may show up as a side effect of running uv here — it is
gitignored on purpose, don't commit it.

## Running the tests

`uvx --with tox-uv tox` is the same invocation CI uses, so a local run and a CI run are the same
thing. It tests against every Python version available locally; `uv python install 3.10 3.13` (and
so on) gets you the ones you're missing, and tox-uv discovers them without any further setup.
`uv python list` shows what you already have.

The `envlist` in `tox.ini` deliberately covers only the oldest and newest supported versions so
local iteration stays fast — the full matrix runs in CI.

Narrow a run down with `-e`, for example `tox -e py314` for a single interpreter or `tox -e style`
for the linters. `tox -l` lists everything available; `tox.ini` is the authority on what each
environment does.

Run tests through the project venv (`.venv/bin/pytest`) or through tox. Invoking pytest via
`python -m pytest` from an unrelated interpreter breaks runez's own `sys.argv` canonicalization and
produces confusing failures.

## Test coverage

Run `tox`, then open `.tox/test-reports/htmlcov/index.html`.

## Before you open a PR

`tox -e style` must pass — see [code quality](./ci/code-quality.md) for what it enforces and why.
`tox -e reformat` applies the mechanical fixes for you.
