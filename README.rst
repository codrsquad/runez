Friendly misc/utils/convenience library.
========================================

.. image:: https://img.shields.io/pypi/v/runez.svg
    :target: https://pypi.org/project/runez/
    :alt: Version on pypi

.. image:: https://travis-ci.org/zsimic/runez.svg?branch=master
    :target: https://travis-ci.org/zsimic/runez
    :alt: Travis CI

.. image:: https://codecov.io/gh/zsimic/runez/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/zsimic/runez
    :alt: codecov

.. image:: https://img.shields.io/pypi/pyversions/runez.svg
    :target: https://github.com/zsimic/runez
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
    first = runez.first_line("foo")
    lines = runez.get_lines("foo")

    full_path = runez.resolved_path("foo/bar")
    folder = runez.parent_folder(full_path)
    runez.ensure_folder(folder)
    with runez.Anchored(folder):
        assert runez.short(full_path) == "bar"


Installation
============

As usual, available on pypi_: ``pip install runez``


.. _pypi: https://pypi.org/
