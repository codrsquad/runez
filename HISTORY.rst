=======
History
=======

1.6.5 (2019-02-25)
------------------

* Added ``runez.config``

* Added ``runez.header()``


1.6.2 (2019-02-22)
------------------

* Modified ``runez.log.setup()``:

    * Renamed ``custom_location`` to ``file_location``

    * Introducing ``console_level``, and ``file_level``


1.5.5 (2019-02-21)
------------------

* Correctly handle ``custom_location``

* Preparing for log file rotation support


1.5.0 (2019-02-19)
------------------

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


1.3.6 (2019-01-24)
------------------

* Added ``Heartbeat``, ``shortened``, ``testing``

* Refactored code to allow for better

* Simplified names::

    JsonSerializable -> Serializable
    run_program()    -> run()
    write_contents() -> write()


1.2.8 (2018-10-01)
------------------

* Initial version
