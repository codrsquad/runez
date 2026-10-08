# Type checkers

runez is not type-tight yet. It grew up before annotations were common, and it leans on patterns —
dynamically-built metaclasses, descriptors, deliberate monkey-patching of `logging` and `sys.stdout`
— that type checkers have genuinely different opinions about. That makes it an unusually good
playground: there is real, ambiguous material to disagree over, rather than a clean codebase where
everything agrees on zero.

## Where this stands

The side-by-side phase is over. runez was one of ~30 codebases in a wider survey of the same six
checkers, and the outcome is to **gate on `ty`**: it caught the most real bugs, at the best
signal-to-noise ratio, with the fewest serious gaps. No checker stands above the others, though —
each one misses real bugs that another catches — so all six keep their tox environment here as
second opinions.

The plan, in stages:

1. **`src/` to zero ty diagnostics**, warnings included. Done, then the other checkers' reports were
   mined for what ty can't see, see [pyrefly](./pyrefly.md) and [zuban](./zuban.md).
2. **`tests/` and the rest of the repo**: done, ty now checks the whole repo. Two rules are relaxed
   for tests only, via `[[tool.ty.overrides]]` in `pyproject.toml`:
   - `redundant-condition`: a test checks some state, calls something, and checks again, while ty
     assumes the call left attributes as they were.
   - `invalid-assignment`, in `test_schema.py` only: `runez.schema`'s declarative fields can't be
     typed, and the module is on its way out.
3. **Gate**: done, `ty` is in `envlist` and in CI, and so are pyrefly, pyright and mypy, which also
   reach zero on the whole repo. All four are deliberately unpinned, like the other CI tools: a new
   release that brings new findings is a heads-up to act on (see [code quality](../ci/code-quality.md)).

Not in CI, on purpose: zuban (AGPL-3.0, and a single maintainer), and basedpyright, which still
reports findings.

pyrefly earned its place next to ty: it infers through unannotated code that ty deliberately leaves
as `Unknown`, so it kept finding things after ty went quiet, see [pyrefly](./pyrefly.md).
pyright did too: it types an unannotated parameter from its default value, so `logger=False` meant
`logger=None` was an error for every pyright user of runez. That is how the shared `fatal`,
`logger` and `dryrun` parameters got their `FatalSpec` / `LoggerSpec` / `DryrunSpec` annotations.

The other two are not driven to zero. What they report is worth reading when it's a real defect,
and worth ignoring when it's one engine's opinion. zuban, for one, checks the bodies of
unannotated functions that mypy skips, see [zuban](./zuban.md).

## No ignore markers

The repo carries no `# type: ignore` (or `# ty: ignore`, `# pyright: ignore`...) markers, and none
should be added. Where a finding is real, fix the code; where it points at a loose signature, fix
the signature. runez ships `py.typed`, so its annotations are a promise to users, and a tighter
signature helps every consumer's type check too.

Two reasons beyond tidiness:

- **A marker is a decision recorded in one checker's dialect.** Each checker honours them
  differently — ty honours only bare `# type: ignore` and its own `# ty: ignore[<rule>]`, and
  silently ignores mypy-style `# type: ignore[<code>]`; basedpyright honours no `# type: ignore` at
  all; pyright honours all of them whatever the code says. The same line ends up invisible to one
  tool and reported by another.
- **A marker can hide more than its line.** mypy carries the wrong type forward past an
  `[assignment]` suppression, hiding a `None` dereference a few lines later.

`cast()` and typing-only `assert`s are suppressions too: they silence a checker without teaching it
anything. Prefer a better annotation.

## The line-up

| Checker | Lineage | Survey take |
| --- | --- | --- |
| ty | Astral | the pick: most bugs caught, best signal ratio; loses a `None` at the first unannotated wrapper |
| pyright | Microsoft | the fallback: fewest findings here, and the only engine to catch the `add_metaclass` bug below |
| pyrefly | Meta | carries `None` furthest through unannotated code; blind to `None` dereferences without its own config section |
| basedpyright | fork of pyright | pyright plus a strictness dial; thousands of "annotate this" warnings at its default mode |
| mypy | the reference implementation | fewest real catches; skips the bodies of unannotated functions by default |
| zuban | reimplementation of mypy's rules | observed non-deterministic on this repo; some verdicts depend on [file order](./zuban.md#the-verdict-on-_prog-depends-on-file-order); AGPL-3.0 |

pytype was dropped early, see [abandoned](./abandoned.md).

## Running them

Each checker is its own tox environment named after it: `tox -e ty`, `tox -e pyright`, and so on.
`tox.ini` and the per-tool sections in `pyproject.toml` are the authority on how each is configured.
All six check the whole repo (basedpyright via `[tool.pyright]`, zuban via `[tool.mypy]`), against
the minimum supported Python (ty reads that from `[project] requires-python`, the others need it
spelled out).

Three of them read a config section that isn't named after them, which is the easiest way to get a
number that means something other than it seems:

- **basedpyright reads `[tool.pyright]`.** It refuses a `pyproject.toml` that has both sections
  ("pick one"), and then silently falls back to defaults — whole repo, the running Python — with
  the parse error visible only under `--verbose`. With no `typeCheckingMode` in `[tool.pyright]`,
  it runs at its own much stricter default.
- **pyrefly adopts `[tool.pyright]` or `[tool.mypy]`** when it has no `[tool.pyrefly]`, and with
  none of them it drops to a preset that does not report a `None` dereference at all. Keep its
  section, even if it ends up empty.
- **zuban reads `[tool.mypy]`**, on purpose: same declared rules, different engine.

basedpyright also resolves imports against the project's `./.venv` rather than the tox env it runs
in, which is why its tox command passes `--pythonpath`. zuban likewise needs `--python-executable`
to see the tox env's packages (it reported missing stubs that were installed right there). The
other four use the tox env.

Snapshot, `src/` only, before stage 1 (on `acf8bcb`) and after it, both on 2026-10-07:

| Checker | Version | Before | After |
| --- | --- | --- | --- |
| ty | 0.0.84 | 24 errors, 5 warnings | 0, on the whole repo too |
| pyright | 1.1.414 | 9 | 0 |
| mypy | 2.4.0 | 64 | 0 |
| pyrefly | 1.3.2 | 98 | 0 |
| basedpyright | 1.40.2 | 124, plus 7698 warnings | 133, plus 7184 warnings |
| zuban | 0.10.0 | 105 | 0 |

**The counts are not comparable between checkers.** They differ in what they look at, and one defect
is a single line for one tool and a dozen for another. Before, ty's volume was mostly
`invalid-assignment`, largely the deliberate monkey-patching.

Config worth knowing about, and what remains:

- **mypy**: two codes are disabled in `[tool.mypy]`. "Missing return statement": falling off the
  end of a function to return `None` is fine, and not a type checker's business. And the
  `annotation-unchecked` note, repeated for every annotated function mypy doesn't check. As for the
  others, `[[tool.mypy.overrides]]` relaxes `test_schema` / `test_serialize` (`runez.schema` is on
  its way out). It also needs `types-psutil` and `types-setuptools`, where the other checkers make do
  without stubs.
- **basedpyright**: its stricter default mode. Mostly uninitialized instance variables (the
  `Slotted` fields, set dynamically) and generics without type arguments (a bare `dict` or
  `Callable`).

## What the survey found in runez

Five real defects, and no checker finds more than two of them. That is the strongest argument for
reading a second opinion before calling something clean.

| Defect | Where | Caught by |
| --- | --- | --- |
| Comparing `Version.components` tuples that mix `int` and `str` raises `TypeError` | `pyenv.py` | ty alone |
| `return_value: _T = None` on an unbound TypeVar | `system.py`, `abort()` | mypy, ty, zuban (implementation only) |
| `add_metaclass`'s inferred return type erases the class it decorates | `serialize.py` | pyright and basedpyright, ≥ 1.1.410 |
| `provider_by_name()` reads `.name`, which only `DictProvider` sets: `AttributeError` with a `PropsfsProvider` | `config.py` | nobody |
| `run()`'s dryrun branch leaves `.output` as `None` unless `stdout` was requested | `program.py` | nobody, here |

- **The first two are fixed.** Commit `7a56d19` had re-introduced them, to see which checkers catch
  them. Reverting it clears all three findings: `components` is all ints again (the post-release
  spelling became a `0`/`1` flag), and `abort()` has a separate overload for when `return_value`
  is given.
- **`add_metaclass` is gone**: it was a py2-era `six` shim, `Serializable` now uses a plain
  `metaclass=MetaInjector`, which every checker understands.
- **`provider_by_name()` is fixed**: it went unreported because `self.providers` started as a bare
  `[]`, so its elements had no type to check. Annotated `list[ConfigProvider]`, all six report the
  attribute (mypy once the method itself is annotated). It now matches on `provider_id()`.
- **The dryrun one is invisible in runez**: setting an attribute in one branch and not the other is
  valid Python. It surfaced as a crash in a consumer that dereferences `.output`. Fixed: `.output`
  and `.error` are now always a `str`, and `run()` is annotated `-> RunResult` (that annotation
  alone was enough for pyright to report both crash sites downstream). Annotating public return
  types is cheap leverage on every consumer's type check.

Same lesson from the other direction: a descriptor whose `__get__` is unannotated and has the usual
`if instance is None: return self` arm makes pyright, pyrefly, basedpyright and zuban report one
finding per use site in consumers. `cached_property` was fixed by subclassing
`functools.cached_property`; `thread_local_property` still has the shape.
