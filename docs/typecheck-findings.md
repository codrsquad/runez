# Type checking: v5.9.1 → v5.10

What v5.10 changed in response to type checker findings on v5.9.1.

| Checker | Version | v5.9.1 | v5.10 | Actionable | Bugs | QOL | Minor |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| ty | 0.0.85 | 87 | 0 | 87 | 2 | 5 | 6 |
| pyrefly | 1.3.2 | 203 | 0 | 203 | 2 | 7 | 5 |
| pyright | 1.1.414 | 164 | 0 | 164 | 1 | 4 | 2 |
| mypy | 2.4.0 | 55 | 0 | 55 | 2 | 5 | 4 |
| basedpyright | 1.40.2 | 11,390 | 10,479 | 2,394 | 2 | 5 | 1 |
| zuban | 0.10.0 | 145 | 0 | 145 | 2 | 7 | 6 |

- **v5.9.1**, **v5.10**: findings on that release's `src/`, `tests/` and `setup.py`, both checked
  with v5.10's settings (`tox.ini`, `pyproject.toml`). v5.10 is the 5.10.x line: its patch releases
  carry incremental fine-tunings.
- **Actionable**: v5.9.1 findings resolved by a change in v5.10.
- **Bugs**, **QOL**, **Minor**: how many of the changes listed under [Bug fixes](#bug-fixes),
  [Quality of life](#quality-of-life) and [Minor](#minor) the checker spotted.
- basedpyright counts include its warnings: 290 errors + 11,100 warnings on v5.9.1, 154 + 10,325 on
  v5.10.
- v5.9.1 had 6 `# type: ignore` comments (what they silenced isn't counted), v5.10 has none.

## Bug fixes

A checker pointed at code that misbehaved.

- `Version` comparisons no longer raise `TypeError` (components mixed `int` and `str`), and
  `post`/`rev`/`r` releases compare equal [ty]
- `RunResult.output` and `.error` are always a `str` (they were `None` when nothing was
  captured) [pyrefly]
- `runez.timezone()` accepts `name=` as a keyword argument (raised `TypeError`) [basedpyright]
- `get_version()` returns a `str` when a module declares `VERSION` as a tuple [mypy]
- `Configuration.provider_by_name()` no longer raises `AttributeError` when a non-dict provider
  is present [all six, once `self.providers` was annotated]
- Methods decorated with `runez.log.timeit` return their result (they always returned `None`)
  [zuban, flagging the ambiguous return type of `Timeit.__call__`]

## Quality of life

Users of runez get accurate types: better checking and IDE completion in their own code.

- `runez.click` properly annotated: option decorators keep the type of what they decorate,
  `command()` and `group()` return click commands, and `click` is imported only where
  needed [ty, mypy, basedpyright, zuban]
- Parameters accepting more than their default suggests are annotated: every `fatal=`, `logger=`
  and `dryrun=` (new public aliases `FatalSpec`, `LoggerSpec`, `DryrunSpec`), and others like
  `overwrite=None` or `run(stdout=None)` [pyright, basedpyright]
- Attributes of `Slotted` classes and of named colors and styles are declared (`runez.log.spec.*`,
  `ColorManager.fg.red`, `PrettyBorder`, ...) [pyrefly, mypy, zuban]
- `abort()` return type follows `fatal` and `return_value` (`NoReturn` when fatal) [ty, pyrefly,
  mypy, zuban]
- `PrettyTable.border` and `.header` typed: assigning a spec converts it, reading gives a
  `PrettyBorder` or `PrettyHeader` [ty, pyrefly, pyright, basedpyright, zuban]
- `RestClient.mock()` and `RestHandler.mock()` have precise signatures (decorator, or decorator
  that is also a context manager) [pyrefly, pyright, basedpyright, zuban]
- `to_epoch()` and `to_epoch_ms()` have precise signatures (a date gives a `float`, `None` gives
  `None`) [pyrefly, pyright, basedpyright]
- Setting `runez.system.AbortException` (e.g. to `SystemExit`) or `runez.date.DEFAULT_TIMEZONE`
  no longer upsets type checkers [ty, pyrefly, mypy, zuban]
- Return types annotated where checkers inferred them wrong: `resolved_path()` (`None` gives
  `None`), `Version.major`, `.minor` and `.patch` (`int | None`), `run()`,
  `find_caller()` [ty, pyrefly, mypy, zuban]

## Removed

A checker flagged code that turned out not to be needed.

- Unused `RestClient` caching (`CacheWrapper`, `RestClient.std_diskcache()`,
  `RestClient(cache=...)`) [ty, pyrefly, pyright, basedpyright, zuban]
- py2-era `add_metaclass()` and `add_meta()`: `Serializable` uses `metaclass=MetaInjector`, which
  every checker understands [ty, pyrefly, pyright, basedpyright, zuban]
- Dead code: an unneeded `Struct.default` property, an always-true check in
  `ActivateColors` [basedpyright, zuban]

## Minor

The checker was right, the fix changes little in practice.

- Deliberate monkey-patching (`sys.stdout.write`, `logging.info()`, `urlopen`, ...) goes through
  `_R.monkeypatch()` [ty, pyrefly, mypy, zuban]
- Variables and attributes hold one type: no rebinding to another type midway, attributes that can
  be `None` say so (`PythonSpec.from_text()`, `compress()`, `LogManager.debug`, `DefaultBehavior`,
  ...) [ty, pyrefly, mypy, zuban]
- `Cli.run_cmds()` aborts with a clear message when it can't find its caller, and its option flags
  are typed `tuple[str, ...] | None` [ty, pyrefly, zuban]
- Attributes holding floats annotated `float` (`Heartbeat`) [ty, pyrefly, zuban]
- Class-level containers annotated (`ClassVar[dict[...]]`, `list[...]`) [mypy]
- Small ones: `requests` version read via `_R.declared_version()`, checksum regex compiled once in
  `_R.lc`, logging level typed `int` [ty, pyright, zuban]
- Tests: optional values checked before use (`assert`, small helpers), patching via
  `monkeypatch`, explicit arguments for the `dt()` helper [ty, pyrefly, pyright, mypy, basedpyright, zuban]

## Not from a type checker

- `github` table border fixed (its separator row was missing the outer pipes)
