import logging
import sys

import runez


def test_scope():
    with runez.CaptureOutput(log=True) as logged:
        # Verify all channels are captured
        logging.debug("hello")
        assert "DEBUG    hello" in logged.pop()

        logging.info("hello")
        assert "INFO     hello" in logged.pop()

        logging.warning("hello")
        assert "WARNING  hello" in logged.pop()

        print("on stdout")
        sys.stderr.write("on stderr")
        assert "on stdout\non stderr" in logged.pop()

    with runez.CaptureOutput(stderr=False) as logged:
        # Verify that when stderr is off, it is not captured
        print("on stdout")
        sys.stderr.write("on stderr")

        assert "on stdout\n" in logged
        assert "on stderr" not in logged


def test_stacked():
    with runez.CaptureOutput(stdout=True, stderr=True, log=True) as logged1:
        # Capture all 3: stdout, stderr, log
        print("print1")
        sys.stderr.write("err1\n")
        logging.info("log1")

        assert "print1" in logged1.stdout
        assert "err1" in logged1.stderr
        assert "log1" in logged1.log

        with runez.CaptureOutput(stdout=True, stderr=False, log=False) as logged2:
            # Capture only stdout on 2nd level
            print("print2")
            sys.stderr.write("err2\n")
            logging.info("log2")

            # Verify that we did capture, and are isolated from prev level
            assert "print1" not in logged2.stdout
            assert "print2" in logged2.stdout

        # Verify that 1st level was not impacted by 2nd level
        assert "print1" in logged1.stdout
        assert "err1" in logged1.stderr
        assert "log1" in logged1.log

        assert "print2" not in logged1.stdout
        assert "err2" in logged1.stderr
        assert "log2" in logged1.log


def test_stacked2():
    with runez.CaptureOutput(stdout=True, stderr=True, log=True) as logged1:
        # Capture all 3: stdout, stderr, log
        print("print1")
        sys.stderr.write("err1\n")
        logging.info("log1")

        assert "print1" in logged1.stdout
        assert "err1" in logged1.stderr
        assert "log1" in logged1.log

        with runez.CaptureOutput(stdout=True, stderr=True, log=True) as logged2:
            # Capture all 3 again at 2nd level
            print("print2")
            sys.stderr.write("err2\n")
            logging.info("log2")

            # Verify that we did capture, and are isolated from prev level
            assert "print1" not in logged2.stdout
            assert "err1" not in logged2.stderr
            assert "log1" not in logged2.log

            assert "print2" in logged2.stdout
            assert "err2" in logged2.stderr
            assert "log2" in logged2.log

        # Verify that 1st level was not impacted by 2nd level
        assert "print1" in logged1.stdout
        assert "err1" in logged1.stderr
        assert "log1" in logged1.log

        assert "print2" not in logged1.stdout
        assert "err2" not in logged1.stderr
        assert "log2" not in logged1.log
