# What pyrefly found after ty went quiet

Once `tox -e ty` reported nothing on `src/`, pyrefly still had 74 findings. Most of them turned out
to be worth acting on. This page keeps track of what they were, and why ty did not see them.

## Why pyrefly sees more here

ty follows the *gradual guarantee*: an unannotated value is `Unknown`, and nothing that flows
through it gets checked. That is a deliberate choice, and it is why ty's report is quiet on
partly-annotated code. pyrefly infers more aggressively from unannotated code, so it reports
problems at boundaries ty treats as opaque.

A quiet ty report on partly-annotated code means "nothing contradictory was found", not "checked".
The fix is usually an annotation, which then helps every checker (ty included) from there on.

Three minimal shapes, each found in runez, each a different difference in policy:

| Shape | ty | pyright | mypy | pyrefly | basedpyright | zuban |
| --- | --- | --- | --- | --- | --- | --- |
| Field declared only in `__slots__`, read | `Unknown`, accepted | accepted | ❌ no attribute | ❌ no attribute | accepted | ❌ no attribute |
| `self.x = 0` in `__init__`, later `self.x = time.time()` | `float` | `int \| float` | `int`, error on the float | `int`, error on the float | `int \| float` | `int`, error on the float |
| `if parent is self.parent: parent.parent` (unannotated `parent`, `Optional` attribute) | silent | silent | silent | ✅ possible `None` | silent | silent |

Measured with ty 0.0.84, pyright 1.1.414, mypy 2.4.0, pyrefly 1.3.2, basedpyright 1.40.2, zuban 0.10.0.

- **`__slots__`-only fields**: ty and the pyright family accept the attribute but know nothing
  about its type; pyrefly, mypy and zuban say it does not exist. Either way nobody checks what is
  done with the value. All six still catch a typo'd attribute name.
- **First assignment wins**: pyrefly, mypy and zuban take an unannotated attribute's type from its
  first assignment in `__init__`, ty and pyright from all assignments. The first policy flags the
  later `float` as a mismatch, the second silently widens.
- **Narrowing an unannotated parameter**: only pyrefly narrows `parent` through `is` to the
  attribute's `Bar | None`, and so sees the dereference of a possible `None`.

## Findings

| Finding | Count | Status |
| --- | --- | --- |
| `Heartbeat` task `next_execution = 0`, later assigned a `float` epoch | 1 | fixed: `next_execution: float = 0` |
| Progress bar `_remove_parent(parent)` / `_remove_progress_bar(bar)`: unannotated, so possibly `None` | 2 | fixed: annotated `ProgressBar` |
| Progress spinner `_has_progress_line` holds 3 states (`None`: last output ended with a newline) | 1 | fixed: annotated `bool \| None`, with a comment |
| `_formatted_text()` returns `None` only in strict mode, but every caller saw `str \| None` (root warning crashed on `.endswith()` if the message was `None`) | 2 | fixed: two overloads on `strict` |
| `_run_popen()` rebinding a `StringIO` variable to the `str` it captured | 2 | fixed: separate variables |
| `RunResult.output` / `.error` default to `None`, though a completed run always sets a `str` (the dryrun branch leaves `None` unless stdout was requested) | 1 | fixed: always a `str`, `""` when nothing was captured; `run()` annotated `-> RunResult` |
| `Cli.run_cmds()` relies on `find_caller()` returning `None` to fail with an `AttributeError` | 6 | fixed: explicit `abort()` with a clear message; `find_caller()` annotated `-> _CallerInfo \| None` |
| `DefaultBehavior.strict` / `.extras`: a `bool` setting at class level, a resolved callable on instances | 2 | fixed: class-level settings renamed `default_strict` / `default_extras` |
| `Slotted` subclasses (`LogSpec`, `NamedColors`, `NamedStyles`, `LoggingSnapshot`) declare fields only via `__slots__` | 56 | fixed: every runez `Slotted` descendant annotates its slots, `tests/test_slotted.py` keeps the two in sync |
| `Renderable.__call__(text: str)` while its body `stringified()`s any object (`protected_main()` passes an exception) | 1 | fixed: `text: object`; surfaced by the `Slotted` annotations, and reported by ty, pyright and pyrefly alike |

With that, pyrefly reports nothing on `src/` either. Annotating the `Slotted` fields also took mypy from 54 to 34
and zuban from 78 to 20 (see [zuban](./zuban.md)): the most widely used settings objects in runez had been unchecked by
every checker.
