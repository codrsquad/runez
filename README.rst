Friendly misc/utils/convenience library
=======================================

.. image:: https://img.shields.io/pypi/v/runez.svg
    :target: https://pypi.org/project/runez/
    :alt: Version on pypi

.. image:: https://github.com/codrsquad/runez/workflows/Tests/badge.svg
    :target: https://github.com/codrsquad/runez/actions
    :alt: Tested with Github Actions

.. image:: https://codecov.io/gh/codrsquad/runez/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/codrsquad/runez
    :alt: Test code codecov

.. image:: https://img.shields.io/pypi/pyversions/runez.svg
    :target: https://github.com/codrsquad/runez
    :alt: Python versions tested (link to github project)


Overview
========

**runez** is a convenience ``"utils"`` library for common operations I found myself rewriting multiple times.

The name was initially meant as "run ez" ("run easy"),
the fact that it sounds like "runes" gives it a bit of a mystery/magic side that's also relatively appropriate
(it does indeed concentrate a bit of invocation magic, as you can save quite a few lines of repetitive code by using it)


Features
========

- Usable with any python version

- Pure python standalone library, does not bring in any additional dependency

- Takes care of most edge cases, with nice errors

  - Functions can be called without checking for return code etc (abort by default, with nice error)

  - They can also be called with ``fatal=False``, in which case the return value will indicate whether call succeeded or not

- Support for ``dryrun`` mode (show what would be done, but don't do it)

- Perform most typical logging setups in one call to ``runez.log.setup()``

- Log operations systematically (at debug level mostly), examples::

    Running: foo ...
    Copy foo -> bar
    Would move foo -> bar    (for dryrun)

- ``CaptureOutput`` context manager -> grab output/logging from any code section

- 100% test coverage


Example
=======

Run a program::

    import runez

    # Aborts if "foo" doesn't exist
    output = runez.run("ls", "foo")

    # Output can also be ignored
    runez.run("ls", "foo")

    # Don't capture output, just run the command and let output "pass through"
    runez.run("ls", "foo", stdout=None, stderr=None)

    # Don't abort, return False on failure (or actual output when successful)
    output = runez.run("ls", "foo", fatal=False)


File operations::

    import runez

    runez.touch("foo")
    runez.copy("foo", "bar")
    runez.move("foo", "baz")
    runez.delete("foo")

    runez.write("foo", "bar\nbaz\n")
    content = "\n".join(runez.readlines("foo", first=10))

    full_path = runez.resolved_path("foo/bar")
    folder = runez.parent_folder(full_path)
    runez.ensure_folder(folder)
    with runez.Anchored(folder):
        assert runez.short(full_path) == "bar"


Installation
============

As usual, available on pypi_: ``pip install runez``


Philosophy
==========

``runez`` tries to provide a consistent interface across functions.
Here are the main tenets for functions involving I/O (such as writing, reading, copy-ing files etc):

All IO-related functions **NOT returning content** (``run()``, ``delete()``, ...)
have this common signature: ``fatal=True, logger=UNSET, dryrun=UNSET``

- ``fatal``: decides whether operation should raise an exception on failure or not

  - ``fatal=True`` (default): raise an exception on failure, log a meaningful error

  - ``fatal=False``: don't raise on failure, log a meaningful error

  - ``fatal=None``: don't raise on failure, don't log anything

  - In non-fatal mode, calls try to return a usable value appropriate for the call (see docstring of each function)

- ``logger``: decides how chatty the operation should be

  - ``LOG.error()`` is used for failures, except when ``fatal`` is not True AND provided ``logger`` is a callable

  - ``logger=UNSET`` (default):

    - ``LOG.debug("Running: ...")`` to trace activity

    - ``print("Would run: ...")`` in dryrun mode

  - ``logger=False``: Log errors only (used internally, to avoid unnecessary log chatter when one operation calls another)

  - ``logger=mylogger``: call provided ``mylogger()`` to trace activity (example: ``logger=MY_LOGGER.info``)

    - ``mylogger("Running: ...")`` to trace activity

    - ``mylogger("Would run: ...")`` in dryrun mode

  - ``logger=None``: Don't log anything (even errors)

- ``dryrun`` allows to override current ``runez.DRYRUN`` setting just for that call



All IO-related functions **returning content** (``read_json()``, ``readlines()``, ...)
use a simpler convention based on: ``default=UNSET``,
which decides whether operation should raise an exception on failure or not:

- When ``default`` is **NOT provided**, the function call will abort on failure with an exception,
  logging a meaningful error via ``LOG.error()``

- When ``default`` **is provided** (even if ``None``), the function call will NOT abort,
  but return the specified ``default`` instead, it is up to the caller to log anything
  in that case (no log chatter comes from ``runez`` in that case, at all)


.. _pypi: https://pypi.org/
