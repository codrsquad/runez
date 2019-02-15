import logging
import sys

import runez


def test_logging():
    with runez.CaptureOutput() as logged:
        logging.debug("foo")
        assert "DEBUG    foo" in logged.pop()

        logging.info("foo")
        assert "INFO     foo" in logged.pop()

        logging.warning("foo")
        assert "WARNING  foo" in logged.pop()

        print("on stdout")
        sys.stderr.write("on stderr")
        assert "stdout: on stdout\nstderr: on stderr" in logged.pop()

    with runez.CaptureOutput(streams=[sys.stdout]) as logged:
        print("on stdout")
        sys.stderr.write("on stderr")

        assert "on stdout\n" in logged
        assert "on stderr" not in logged
