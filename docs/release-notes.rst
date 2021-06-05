=======
History
=======

2.7.5 (2021-06-04)
-----------------

* Moved development related functions to ``runez.DEV``


2.7.4 (2021-06-04)
-----------------

* Added ``{project}`` placeholder for ``runez.log.setup()``

* Updated code to use ``SYS_INFO`` instead of deprecated ``runez.log`` calss


2.7.3 (2021-06-03)
-----------------

* Allow ``dict`` source for ``two_column_diagnostics()`` render


2.7.2 (2021-06-03)
-----------------

* Added ``cached_property.to_dict()``


2.7.1 (2021-06-02)
-----------------

* Resilient ``CurrentFolder()`` in dryrun mode


2.7.0 (2021-05-28)
-----------------

* Added ability to ``run()`` a command in background

* Added ``SYS_INFO.program_name``


2.6.17 (2021-05-26)
------------------

* ``find_python()`` accepts ``PythonInstallation`` objects


2.6.16 (2021-05-25)
------------------

* Allow to represent ``PythonSpec`` in custom/colored ways


2.6.15 (2021-05-24)
------------------

* Don't crash if python version could not be determined


2.6.14 (2021-05-22)
------------------

* Better error report in ``runez.run()`` when program is not installed


2.6.13 (2021-05-22)
------------------

* ``Version.from_text()`` can extract version from chatty text


2.6.12 (2021-05-21)
------------------

* Don't rely on ``VIRTUAL_ENV`` env var to determine ``dev_folder()``


2.6.11 (2021-05-12)
------------------

* Try harder with ``get_version()``: use importlib.metadata when available


2.6.9 (2021-05-08)
------------------

* ``runez.run(passthrough=True)`` now properly lets terminal colors through

* Added ``runez.inspector.auto_install()``


2.6.8 (2021-05-02)
------------------

* Added ``PythonDepot.scanned_prefixes``


2.6.7 (2021-05-01)
------------------

* Allow to split CamelCase words as well via ``runez.words(decamel=True)``


2.6.6 (2021-04-26)
------------------

* Corrected diagnostics, added ``transform=`` argument to ``flattened()``


2.6.5 (2021-04-26)
------------------

* Corrected ``joined()``


2.6.4 (2021-04-25)
------------------

* Corrected bug in ``cached_property``


2.6.3 (2021-04-23)
------------------

* ``PythonSpec`` is now hashable


2.6.2 (2021-04-22)
------------------

* Removed ``python_version()`` (``runez.pyenv`` is better suited for this)

* Accept ``invoker`` as python spec


2.6.0 (2021-04-21)
------------------

* Removed ``@chill_property``, not general/useful enough


2.5.9 (2021-04-09)
------------------

* Properly handle multiple lines in ``flattened(split=...)``


2.5.8 (2021-04-08)
------------------

* Removed ``origin`` and ``family`` from ``PythonDepot``, allow to provide custom scanners


2.5.7 (2021-04-06)
------------------

* Added a reusable way of showing diagnostics

* Moved

  * ``runez.TERMINAL_INFO`` -> ``runez.SYS_INFO.terminal``

  * ``runez.log.current_test()`` -> ``runez.SYS_INFO.current_test()``

  * ``runez.log.dev_folder()`` -> ``runez.SYS_INFO.dev_folder()``

  * ``runez.log.program_path()`` -> ``runez.SYS_INFO.program_path``

* Added ``runez.shell()`` for quick shell command output grab

* Allow to specify package in ``auto_import_siblings()``

* Complain if running as root (by default) in ``runez.log.setup()``


2.5.6 (2021-03-31)
------------------

* Added ``passthrough`` option for ``runez.run()`` (capture output, and let it pass-through)

* Added ``TerminalProgram``, detection of parent terminal (if any)


2.5.5 (2021-03-31)
------------------

* Export class ``PsInfo`` instead of function ``ps_info``


2.5.4 (2021-03-30)
------------------

* Allow to reorder python installation origins and families

* Use same ``PythonInstallation`` class for all origins


2.5.1 (2021-03-18)
------------------

* Don't use globals in ``PythonDepot``

* Better formalized what is logged by ``read_json()`` and ``readlines()``

* Respect ``logger=None`` (no log chatter at all), vs ``logger=False`` (fall back to trace)


2.5.0 (2021-03-11)
------------------

* Added ``runez.pyenv`` module


2.4.11 (2021-03-10)
-------------------

* Corrected bug with progress stdout/err re-capture

* Show sorted import times in ``import-speed`` command


2.4.9 (2021-02-15)
------------------

* Don't hide cursor in progress spinner, so we can't ever miss not showing it back

* Simplified how logsetup references are resolved


2.4.5 (2021-01-20)
------------------

* Added ``ProgressBar``, corrected flickering in spinner


2.3.9 (2021-01-12)
------------------

* Added progress spinner, can be activated with ``runez.log.progress.start()``

* Corrected bug in ``{argv}`` expansion


2.3.4 (2021-01-11)
------------------

* Renamed ``terminal_info()`` -> ``TERMINAL_INFO``, moved ``is_tty()`` to it

* Using ``monkeypatch`` instead of ``mock``

* Added ``runez.log.trace()``


2.3.3 (2020-12-27)
------------------

* Moved to https://github.com/codrsquad/runez

* Better signature for ``terminal_width()``

* Added ``@cached_property``, ``@chill_property``, ``is_basetype()``, ``is_iterable()``, ``joined()``, ``parsed_tabular()``, ``ps_info()``

* Added ``runez.click.prettify_epilogs()``

* Added ``attributes_by_type()`` to schema meta, ``Struct`` schema type (for non-root serializable objects)

* Consistent signature for ``first_line()``, ``flattened()``, ``joined()``, ``json_sanitized()``, ``ini_to_dict()``, ``quoted()``

* ``runez.run()`` strips newlines only on captured content


2.2.3 (2020-12-06)
------------------

* Allow for workaround around py3 unable to sort None-keys in json.dumps(sort_keys=True)

* ``short()`` defaults now to terminal width

* ``represented_json()`` and ``save_json()`` have now a signature consistent with ``json_sanitized()``

* Accept optionally multiple paths at once in ``Anchored()`` context manager


2.1.8 (2020-11-04)
------------------

* Correctly expand ~ in path, if provided

* Allow to override the internal default logger, used in ``runez.run()`` etc

* Restored default ``click.version()`` message, to minimize differences with click

* Simplified default ``click.version()`` message, now simply outputs version (without fluff)

* Use module's ``__version__`` when available

* Moved to github actions

* Added ``FallbackChain``

* Corrected edge case with ``cli.run(..., exe=)``

* Ignore errors when deleting temp folders in context managers

* ``runez.log.dev_folder()`` now accepts relative path

* Renamed ``runez.conftest.resource_path()`` to ``runez.log.tests_path()``

* Added ``runez.log.project_path()``

* Allow to override ``sys.executable`` in click test runs


2.0.19 (2020-10-01)
-------------------

* Adapted to latest pytest log wrapping

* Corrected date conversion for empty string

* Allow to not wait for spawned process with ``runez.run(fatal=None, stdout=None, stderr=None)``

* More consistent debug logging on file operations

* Corrected edge case in py2 with coloring of ``μ`` character in ``represented_duration()``

* Added ``clean=True`` option to ``ensure_folder()``

* Added ``click.border()`` option

* Bug fixes

* Reviewed all IO related functions and made them respect the same signature, explained in doc:

  * Functions not returning content (``run()``, ``delete()``, ...) all have this signature:
    ``fatal=True, logger=UNSET, dryrun=UNSET``

  * Functions returning content (``read_json()``, ``readlines()``, ...) are simplified to just a:
    ``default=UNSET`` (aborts on failure when no ``default`` is specified,
    ``default`` returned otherwise).

* Simplified signatures of: ``ensure_folder``, ``read_json``, ``readlines``

* Made ``readlines`` consistent with all other IO related functions

* Defined signature of ``abort()``, not going via ``**kwargs`` anymore

* Added adhoc "linter" to ensure IO related functions have a consistent signature

* Bug fixes, renamed ``test_resource`` to ``resource_path`` (in ``runez.conftest``),
  to avoid pytest thinking it is a test function when imported.

* Fixed docstrings, ``RunResult`` properly evaluates to true-ish on success

* ``runez.run()`` now always returns a ``RunResult``

* ``runez.run()`` now returns a ``RunResult`` object when called with ``fatal=None``,
  with fields: ``.output``, ``.error`` and ``.exit_code``

* Removed ``include_error`` kwarg from ``runez.run()``, ``RunResult.full_output`` can now be used instead

* Internal refactor to minimize import time (import time now tested, must be less than 3x slower than ``import sys``)

* Renamed:

    * ``first_meaningful_line()`` -> ``first_line()`` applies to strings or list (not file anymore)
    * ``shortened()`` -> ``short()``
    * ``represented_args()`` -> ``quoted()`` (can quote a single string, or a list of strings)

* Replaced named arg ``separator`` to be more indicative as to what it used for

    * ``delimiter`` when the string is used to ``.join()`` a list of things back to a string
      (eg: ``represented_bytesize(.., delimiter=" ")``)
    * ``split`` when the character is used to split strings (eg: ``flattened(.., split=",")``
    * ``flattened()`` now has boolean optional parameters (instead of previously ``split`` enum)

* Reduced number of things exported at top-level, removed:

    * ``heartbeat``, use ``from runez.heartbeat import ...``
    * ``prompt``, use ``from runez.prompt import ...``
    * ``represent``, use ``from runez.render import ...``
    * ``schema``, use ``from runez.schema import ...``
    * ``thread``, use ``from runez.thread import ...``
    * ``set_dryrun`` (better applied via ``runez.log.setup()``)
    * ``SANITIZED, SHELL, UNIQUE``, function ``flattened()`` now accepts more explicit boolean flags
    * ``class_descendants()``: not so useful after all, using decorators is better

    * ``auto_import_siblings``, use ``from runez.inspector import auto_import_siblings``

    * ``capped``, use ``runez.config.capped``
    * ``ActivateColors``, use ``runez.colors.ActivateColors``
    * ``is_coloring``, use ``runez.color.is_coloring``
    * ``SECONDS_IN_ONE_*``, use ``runez.date.SECONDS_IN_ONE_*``
    * ``ini_to_dict``, use ``runez.file.ini_to_dict``
    * ``is_younger``, use ``runez.file.is_younger``
    * ``current_test``, use ``runez.log.current_test``
    * ``dev_folder``, use ``runez.log.dev_folder``
    * ``find_parent_folder``, use ``runez.log.find_parent_folder``
    * ``program_path``, use ``runez.log.program_path``
    * ``require_installed``, use ``runez.program.require_installed``
    * ``align``, use ``from runez.render import Align``
    * ``header``, use ``from runez.render import Header``
    * ``PrettyTable``, use ``from runez.render import PrettyTable``
    * ``json_sanitized``, use ``runez.serialize.json_sanitized``

* Enhanced:

    * ``quoted()`` can quote a single string, or a list of strings
    * ``readlines()`` can now ignore empty lines, and return up to N first lines

    * Relevant click decorators are not exposed anymore by default, and auto-apply themselves:

        * ``@runez.click.color()``
        * ``@runez.click.config()``
        * ``@runez.click.dryrun()``

* Added:

    * ``PrettyTable``, more flexible than the now abandoned and similar https://pypi.org/project/PrettyTable
    * ``runez.inspector`` module, which mostly acts on context (auto-detects caller), and provide a few relevant features:

        * ``auto_import_siblings()``: automatically finds all siblings of calling module, and ensure
          every single one is ``import``-ed, this is useful to avoid having to manually register ``click``
          sub-commands of a large group
        * ``run_cmds()``: poor man's ``click``-replacement, finds all ``cmd_`` functions in caller module
          and makes a multi-command out of them, with ``--help`` etc


1.8.8 (2019-05-23)
------------------

* ``get_version()`` can now be silent

* Removed ``get_caller_name()``

* ``runez.log.setup()`` can now be called multiple times, to setup logs iteratively


1.7.7 (2019-04-23)
------------------

* Hint type of ``runez.conftest.cli`` for PyCharm's auto-complete

* Added support for ``ignore=[...]`` in ``copy()``

* Strip trailing spaces by default when saving pretty-printed json

* Better information when ``verify_abort()`` fails

* Added ``runez.log.spec.clean_handlers`` (``True`` by default), to automatically cleanup any pre-existing ``logging.root.handlers``

* Renamed ``to_json`` -> ``from_json`` (to avoid confusion)

* Augmented all docstrings to accept ``str`` or ``unicode``, to avoid type-check warnings in python 2.7

* Allow stacked ``CaptureOutput``


1.6.12 (2019-03-07)
-------------------

* Better heartbeat

* ``runez.log.setup(rotate=)`` raises more descriptive ``ValueError`` if bogus value passed

* Added ``runez.config`` and ``runez.click.config``

* Added ``runez.header()``

* Auto-simplify ``sys.argv`` when running tests in pycharm

* Removed ``prop`` (wasn't useful after all)

* Modified ``runez.log.setup()``:

    * Renamed ``custom_location`` to ``file_location``

    * Introducing ``console_level``, and ``file_level``


1.5.5 (2019-02-22)
------------------

* Correctly handle ``custom_location``

* Preparing for log file rotation support

* Introduced ``runez.UNSET`` to distinguish between values not provided vs ``None`` (to avoid confusion)

* ``custom_location=`` instead of ``location=`` in ``runez.log.setup()``

* ``custom_location`` is now part of ``runez.log.spec``
  (meaning it can be set via ``log.setup()``, or via ``log.spec.set()``, just like all other settings)


1.4.4 (2019-02-18)
------------------

* Removed ``runez.State``, dryrun is now in ``runez.DRYRUN``

* Removed ``runez.debug()``, ``runez.info()`` etc, use ``runez.log.setup()`` then simply calls to ``logging.debug()`` etc

* Added ``runez.log.setup()``, a convenient way of performing typical logging setup in one line


1.3.6 (2019-01-24)
------------------

* Added ``basename`` and ``prop``

* Added ``Heartbeat``, ``shortened``, ``testing``

* Refactored code to allow for better

* Simplified names::

    JsonSerializable -> Serializable
    run_program()    -> run()
    write_contents() -> write()


1.2.8 (2018-10-01)
------------------

* Initial operational version
