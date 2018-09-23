Convenience methods for file/process operations
===============================================

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

**runez** is a small convenience library for common operations I found myself rewriting multiple times.

It comes in handy for programs that need to run other programs, or copy/move files etc.

Features
========

- Support for ``dryrun`` mode (show what would be done, but don't do it)

- Log operations systematically (at debug level mostly), examples::

    Running: foo ...
    Copy foo -> bar
    Would move foo -> bar    (for dryrun)

- ``CaptureOutput`` context manager -> grab output/logging from any code section

- Take care of most edge cases, with nice errors

- Functions can be called without checking for return code etc (abort by default, with nice error)

- They can also be called with ``fatal=False`` for inspection

- 100% test coverage


Example
=======

Run a program::

    import runez

    # Aborts if "foo" doesn't exist
    runez.run_program("ls", "foo")

    # Doesn't abort, returns None instead (returns output when successful)
    output = runez.run_program("ls", "foo", fatal=False)


File operations::

    import runez

    runez.touch("foo")
    runez.copy("foo", "bar")
    runez.move("foo", "baz")
    runez.delete("foo")

    runez.write_contents("foo", "bar\nbaz\n")
    first = runez.first_line("foo")
    lines = runez.get_lines("foo")

    runez.ensure_folder("foo/bar")
    parent = runez.parent_folder("foo/bar")
    full_path = runez.resolved_path("foo/bar")
    assert runez.short(full_path, anchors=parent) == "bar"


Installation
============

As usual, available on pypi_: ``pip install runez``


.. _pypi: https://pypi.org/
