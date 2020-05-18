=======
History
=======

2.0
---

* ``flattened()`` now has boolean optional parameters (instead of previously ``split`` enum)

* ``quoted()`` can quote a single string, or a list of strings

* Renamed:

    * ``formatted()`` -> ``expanded()``
    * ``shortened()`` -> ``short()``

* ``first_line()`` applies now to file, or list of strings, replaces ``first_meaningful_line()``

* ``readline()`` enhanced, can now ignore empty lines, and return up to N first lines

* Added ``PrettyTable``, more flexible than the now abandoned and similar https://pypi.org/project/PrettyTable

* Added ``runez.inspector`` module, which mostly acts on context (auto-detects caller), and provide a few relevant features:

    * ``auto_import_siblings()``: automatically finds all siblings of calling module, and ensure
      every single one is ``import``-ed, this is useful to avoid having to manually register ``click``
      sub-commands of a large group
    * ``run_cmds()``: poor man's ``click``-replacement, finds all ``cmd_`` functions in caller module
      and makes a multi-command out of them, with ``--help`` etc

* Relevant click decorators are not exposed anymore by default, and auto-apply themselves:

    * ``@runez.click.color()``
    * ``@runez.click.config()``
    * ``@runez.click.dryrun()``

* Not-so-useful functions were removed, or not exposed in ``runez.`` anymore:

    * ``SANITIZED, SHELL, UNIQUE``, function ``flattened()`` now accepts more explicit boolean flags
    * ``represented_args()``: now ``quoted()`` can be used instead
    * ``set_dryrun()`` (better applied via ``runez.log.setup()``)
    * ``class_descendants()``: not so useful after all, using decorators is better

* Internal refactor to minimize import time (import time now tested, must be less than 3x slower than ``import sys``)



1.8.1 (2019-05-07)
------------------

* ``get_version()`` can now be silent

* Removed ``get_caller_name()``


1.8.0 (2019-05-06)
------------------

* ``runez.log.setup()`` can now be called multiple times, to setup logs iteratively


1.7.7 (2019-04-23)
------------------

* Hint type of ``runez.conftest.cli`` for PyCharm's auto-complete


1.7.6 (2019-04-10)
------------------

* Added support for ``ignore=[...]`` in ``copy()``


1.7.5 (2019-03-25)
------------------

* Strip trailing spaces by default when saving pretty-printed json


1.7.4 (2019-03-21)
------------------

* Better information when ``verify_abort()`` fails


1.7.3 (2019-03-19)
------------------

* Added ``runez.log.spec.clean_handlers`` (``True`` by default), to automatically cleanup any pre-existing ``logging.root.handlers``


1.7.2 (2019-03-15)
------------------

* Renamed ``to_json`` -> ``from_json`` (to avoid confusion)

* Augmented all docstrings to accept ``str`` or ``unicode``, to avoid type-check warnings in python 2.7


1.7.1 (2019-03-11)
------------------

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


1.5.5 (2019-02-21)
------------------

* Correctly handle ``custom_location``

* Preparing for log file rotation support

* Introcuced ``runez.UNSET`` to distinguish between values not provided vs ``None`` (to avoid confusion)

* ``custom_location=`` instead of ``location=`` in ``runez.log.setup()``

* ``custom_location`` is now part of ``runez.log.spec``
  (meaning it can be set via ``log.setup()``, or via ``log.spec.set()``, just like all other settings)


1.4.4 (2019-02-18)
------------------

* Removed ``runez.State``, dryrun is now in ``runez.DRYRUN``

* Removed ``runez.debug()``, ``runez.info()`` etc, use ``runez.log.setup()`` then simply calls to ``logging.debug()`` etc

* Added ``runez.log.setup()``, a convenient way of performing typical logging setup in one line


1.3.7 (2019-02-08)
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

* Initial version
