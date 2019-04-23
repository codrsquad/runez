=======
History
=======

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
