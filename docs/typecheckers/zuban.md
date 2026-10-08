# What zuban found after ty went quiet

Once ty and pyrefly reported nothing on `src/`, zuban still had 20 findings. zuban reads
`[tool.mypy]`, so it has the same declared rules as mypy, but its engine is different. About half of
the findings were real under-annotations, the rest were zuban's own. This page keeps track of both.

## Why zuban sees more here

**zuban checks the bodies of unannotated functions.** mypy skips them unless `check_untyped_defs`
is on, and most of runez's code is still unannotated. So with the same `[tool.mypy]`, zuban reports
in places mypy does not look at all. Turning on `--check-untyped-defs` makes mypy agree with zuban
on the import fallback below, and on nothing else in this table.

**It also takes unannotated initializers literally.** ty and the pyright family read an
unannotated `{}` or `None` as "not known yet". zuban reads them as the actual type, so a bare
`ClassVar = {}` gets a `.get()` that can only return `None`.

| Shape | ty | pyright | mypy | pyrefly | basedpyright | zuban |
| --- | --- | --- | --- | --- | --- | --- |
| `_cached: ClassVar = {}`, then `if cls._cached.get(key) is not None:` | accepted | accepted | ❌ needs annotation | accepted | accepted | ❌ unreachable |
| `except ImportError: Command = None` in an unannotated function | accepted | accepted | skipped (❌ with `--check-untyped-defs`) | accepted | accepted | ❌ `None` is not `type[Command]` |
| `if t:` then `t[1]`, `t[:3]`, on a `tuple[int, ...]` | accepted | accepted | accepted | accepted | accepted | ❌ index out of range, ambiguous slice |
| Unannotated `@property` getter reading an attribute only its setter assigns | accepted | accepted | accepted | accepted | accepted | ❌ name already defined |
| Class-level `_prog = None`, assigned in one method, read in another | accepted | accepted | accepted | accepted | accepted | ❌ unreachable, depending on file order |

Measured with ty 0.0.84–0.0.85, pyright 1.1.414, mypy 2.4.0, pyrefly 1.3.2, basedpyright 1.40.2,
zuban 0.10.0.

- **Bare `ClassVar = {}`**: a real gap. mypy and zuban both point at it, mypy as a missing
  annotation and zuban as unreachable code. The other four see `Unknown` and check nothing.
- **Import fallback assigned `None`**: a well-known mypy complaint, which mypy here never got to
  see. The fallback was better written as an early return anyway.
- **Truthy variadic tuple**: zuban narrows a truthy `tuple[int, ...]` to "at least one item", and
  then rejects indexing it at `[1]`. That is stricter after the check than before it, since `[1]`
  on the plain `tuple[int, ...]` is accepted. The two "ambiguous slice" errors and the
  `LiteralString` one cascade from the same narrowing. The code was correct.
- **Unannotated property setter**: a zuban bug. To type the getter it needs the attribute the
  setter assigns, which needs the property being defined, and it reports that cycle as a
  redefinition. Annotating the getter makes it go away.
- **File order**: see below.

## The verdict on `_prog` depends on file order

`Cli._prog = None` at class level, assigned in `run_cmds()` and read in `parser()`. Whether zuban
reports the read as unreachable depends on which module it checks first. Two files are enough to
reproduce it: `cli.py` with that class, and another module that calls the method reading `_prog`.

- `zuban check app.py cli.py` reports it, `zuban check cli.py app.py` does not.
- `zuban check .` sorts by filename, so renaming the caller from `app.py` to `zapp.py` makes the
  finding disappear.

In runez, `__main__.py` sorts before `click.py` and calls `runez.cli.parser()`, so the report shows
up. It looks like zuban settles the attribute's type the first time it is needed: when that need
comes from another module, only the class-level `None` has been seen.

The survey observed zuban's count flapping between runs on runez, on a diagnostic that was also
about an unannotated attribute. A check order that varies
between runs would explain that. This is a hypothesis, not verified.

The finding was still worth acting on: `_prog: str | None = None` states what the attribute holds,
and makes the order irrelevant.

## Findings

| Finding | Count | Status |
| --- | --- | --- |
| `Cli._prog = None`: taken to be always `None`, so the `"%s %s"` prefixing was unreachable and the later assignment an error | 3 | fixed: `_prog: str \| None = None` |
| `PythonSimpleInspection._cached: ClassVar = {}`: unparametrized, so both cache hits were "unreachable" | 2 | fixed: `ClassVar[dict[Path, tuple[Path, PythonSimpleInspection]]]` |
| `ClickRunner._run_main()` assigned `None` to the click classes when click isn't installed | 2 | fixed: `_run_click_main()` returns early instead |
| `ClickRunner.project_folder` / `.tests_folder` declared `-> str`, but returned `DEV`'s `str \| None` | 2 | fixed: assert with a clear message (only relevant to tests, which always have a project folder) |
| `ClickRunner` captures built from `stdout and self.logged.stdout`, so an element could be `False` | 1 | fixed: keep only the wanted, non-`None` captures |
| Assigning to a method: heartbeat's `t.execute`, and the patching of `HTTPConnectionPool.urlopen` | 3 | fixed: `_R.monkeypatch()` |
| `RestClient._checksum_regex`, a class attribute created on first use through `getattr()` | 1 | fixed: `_R.lc.rx_checksum_url` |
| `Version.main` / `.minor` / `.patch`, after the truthy-tuple narrowing | 5 | zuban only, the code was correct. Reworked anyway: `_given_component(index)` checks the length right where it indexes |
| `Struct.default`, a property and setter around `_default` | 1 | zuban bug. The property only passed through the attribute `Any.__init__` sets, so it was removed |

With that, zuban reports nothing on `src/` either.

## On the whole repo

Once `[tool.mypy]` covered `tests/` and `setup.py` (for mypy, which gates in CI), zuban followed,
with 19 findings. Two things stood out:

- **zuban doesn't use the environment it runs in.** Without `--python-executable`, it reported
  missing stubs for setuptools while `types-setuptools` was installed in the very tox env running
  it. Its tox command now passes `--python-executable {envpython}`, much like basedpyright needs
  `--pythonpath`.
- **One untyped decorator hides a typed one above it.** With `@runez.click.group()` over
  `@runez.click.debug()`, zuban gave the decorated function its own signature, as if neither
  decorator was there, so `@my_group.command()` failed. `group()` was typed, `debug()` was not.

| Finding | Count | Status |
| --- | --- | --- |
| `setup.py`: "Library stubs not installed for setuptools", although they were | 1 | fixed: `--python-executable {envpython}` |
| `@runez.click.group()` over an untyped option decorator, then `@my_group.command()` | 2 | fixed: `runez.click.option()` and the helpers built on it return `Callable[[_FC], _FC]`, like click's own `option()`. Every checker gains from it: they all saw `(f: Unknown) -> Unknown` |
| Recheck after a call (`assert x is None`, call, `assert x`): the rest of the test "unreachable" | 9 | the basic shape of a test: `warn_unreachable = false` for `tests.*`, as with ty's `redundant-condition` |
| Schema-style fields compared to `None` (`pp.age is None`, where `age = Date`): "unreachable" | 2 | same override, `runez.schema` is on its way out |
| `assert runez.abort(..., fatal=False) is None`: "does not return a value" | 1 | asserting the `None` on purpose: `func-returns-value` off for `tests.*` |
| A test reusing `sections` for a value of another shape | 1 | fixed: second one renamed |
| A test setting `depot.invoker = None`, where `invoker` is a `PythonInstallation` | 1 | fixed: `monkeypatch.setattr()`. Annotating `invoker` as optional would make `find_python()` possibly return `None`, which isn't its contract |
| `dt(*args, **kwargs)` calling `datetime(*args, tzinfo=..., **kwargs)`: `*args` could fill `tzinfo` positionally | 1 | left: technically true, and no caller does it |
| `@classmethod` over `@runez.log.timeit()`: `"Any \| Timeit" not callable` | 1 | left: `Timeit` is both a decorator and a context manager, its `__call__` returns either the result or `self` |

zuban now reports those last 2 on the whole repo, and nothing on `src/`.
