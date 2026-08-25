# Code quality

`tox -e style` is the gate. It runs three things: ruff's linter, ruff's formatter in check mode,
and `tests/extra-validations`. `tox -e reformat` is the same tooling with the fixes applied
instead of reported.

## Ruff: `select`, not `extend-select`

The rule list in `pyproject.toml` is under `[tool.ruff.lint] select`. Do not change it back to
`extend-select`.

`extend-select` means "ruff's defaults, **plus** these". Ruff's defaults are not a stable set —
they have grown substantially across releases, and because nothing in the repo names them, the
enabled rule set changes underneath you when ruff updates. That is not hypothetical here: a ruff
upgrade once turned a green build into hundreds of findings with no repo change, almost all of
them from newly-defaulted families flagging deliberate style choices (`%`-formatting, magic
values) rather than defects.

`select` means "**exactly** these". The enabled set is then fully described by a file that is
checked in and reviewed, which is the property worth having.

When picking up a rule family that a default set used to provide for free, add it explicitly and
look at what it actually reports first. The pylint-error family (`PLE`) is the cheapest thing to
re-add if you want more real-bug coverage — it is small and finds genuine mistakes. The volume
families (`UP`, `PLR`) are mostly opinion about style this project has already chosen against.

## The part `select` doesn't fix

`select` stops the *default set* from drifting. It does not stop a new rule from stabilizing out
of preview into a prefix that is already selected — pick `"B"` and you get whichever bugbear rules
exist in whatever ruff version happens to install. CI installs its tools fresh on every run, so
that is a live path to a build breaking with no commit behind it.

The mitigation is pinning the tool versions in `tox.ini`. Check what is actually pinned there
before assuming; if a build fails on a rule nobody added, compare the ruff version first.

The same reasoning applies to the type-checker environments and, more sharply, to anything still
on a `0.x` version, where behaviour changes between releases are expected rather than exceptional.

For the analogous problem one layer up — GitHub Actions updating themselves — see
[GitHub Actions versions](./github-actions.md).

## extra-validations

`tests/extra-validations` is a small project-specific linter that enforces two conventions no
off-the-shelf tool knows about:

- **`__init__.py` stays coherent.** The order of the `from ... import ...` lines must match the
  order of `__all__`, so nothing gets exported without being declared or drifts out of sync.
- **The shared IO parameters are documented identically everywhere.** runez functions that take
  `fatal`, `logger` or `dryrun` all mean the same thing by them, so their docstring lines must be
  literally the same text across the API, and functions are grouped by which of these they accept.

It parses the source with `ast` and prints the categorization it derived, so its output doubles as
a map of which functions are IO operations, getters, dryrun-aware or tracers. Read the script for
the exact rules — it is short and it is the authority.

## Type checking

Type checking lives in its own tox environments rather than in `style`, and `tox.ini` is the
authority on which checkers are wired up and whether CI currently gates on them. Several are set up
side by side right now — see
[type checkers](../typecheckers/index.md) for why, and why the repo
deliberately carries no `# type: ignore` markers at the moment. runez ships
`py.typed`, so its annotations are part of the contract users see — treat a type error as a design
signal about the signature, not as something to silence with an ignore comment.
