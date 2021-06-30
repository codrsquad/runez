import pytest

import runez


def speedup(monkeypatch):
    # adjust default retry settings so test don't take too long to run
    monkeypatch.setattr(runez.system.RetryHandler, "tries", 5)
    monkeypatch.setattr(runez.system.RetryHandler, "delay", 0)
    monkeypatch.setattr(runez.system.RetryHandler, "backoff", 1)
    monkeypatch.setattr(runez.system.RetryHandler, "jitter", 0)


def test_retry_basic(logged, monkeypatch):
    # Most common use case: decorating a function
    speedup(monkeypatch)

    @runez.retry
    def fail_simple():
        raise Exception("simple failed")

    with pytest.raises(Exception):
        fail_simple()
    assert "simple failed, retrying" in logged.pop()

    @runez.retry(tries=2)
    def fail_quick():
        raise Exception("quick failed")

    with pytest.raises(Exception):
        fail_quick()
    assert "quick failed, retrying" in logged.pop()


def test_retry_class(logged, monkeypatch):
    # Decorating a class function, including with a custom decorator
    speedup(monkeypatch)
    custom_retry = runez.retry(tries=1)

    class SomeSample:
        def __init__(self, fail_count):
            self.fail_count = fail_count

        @runez.retry
        def oopsie(self):
            self.fail_count -= 1
            if self.fail_count:
                raise Exception("oops %s" % self.fail_count)

            return "success"

        @custom_retry
        def custom_fail(self):
            raise Exception("custom failed")

        @custom_retry
        def all_good(self, message):
            return message

    sample = SomeSample(3)
    assert sample.oopsie() == "success"
    output = logged.pop()
    assert "oops 1, retrying" in output
    assert "oops 2, retrying" in output

    assert sample.all_good("ok") == "ok"
    assert not logged

    with pytest.raises(Exception):
        assert sample.custom_fail()
    assert not logged  # Only one retry... no "retrying" message gets logged


def test_retry_custom(logged, monkeypatch):
    # Custom decorator, obtained by calling/storing runez.retry()
    speedup(monkeypatch)
    custom_retry = runez.retry(tries=2)

    @custom_retry
    def failing_call():
        raise Exception("failed")

    with pytest.raises(Exception):
        failing_call()
    assert "failed, retrying" in logged.pop()


def test_retry_handler():
    rh = runez.system.RetryHandler(exceptions=KeyError, tries=1, delay=0, max_delay=None, backoff=1, jitter=0)
    assert str(rh) == "retry(exceptions=KeyError, tries=1, delay=0, max_delay=None, backoff=1, jitter=0)"

    rh = runez.system.RetryHandler(exceptions=(KeyError, ValueError), tries=1, delay=0, max_delay=5, backoff=None, jitter=None)
    assert str(rh) == "retry(exceptions=(KeyError, ValueError), tries=1, delay=0, max_delay=5, backoff=None, jitter=None)"

    # Verify bounds enforced
    with pytest.raises(ValueError) as exc:
        runez.system.RetryHandler(tries=0)
    assert "'tries' value 0 is lower than minimum 1" in str(exc)

    with pytest.raises(ValueError) as exc:
        runez.system.RetryHandler(delay=-1)
    assert "'delay' value -1 is lower than minimum 0" in str(exc)

    with pytest.raises(ValueError) as exc:
        runez.system.RetryHandler(backoff=0)
    assert "'backoff' value 0 is lower than minimum 0.5" in str(exc)

    with pytest.raises(ValueError) as exc:
        runez.system.RetryHandler(jitter=-2)
    assert "'jitter' value -2 is lower than minimum 0" in str(exc)


def test_retry_main(cli):
    cli.run("retry", "-d0", "-j0", "-f2")
    assert cli.succeeded
    assert "Running with 2 max failures, retry(" in cli.logged
    assert "returned successfully" in cli.logged

    cli.run("retry", "-i2", "--timeout", 10)
    assert cli.succeeded
    assert "Running with timeout 10 seconds, retry(" in cli.logged
    assert "2 iterations" in cli.logged


def test_retry_run(logged, monkeypatch):
    speedup(monkeypatch)

    def failing_call(*args, **kwargs):
        # Verify that args correctly passed through (and that _tries=2 was not passed through)
        assert not args
        assert kwargs == dict(x=1)
        raise Exception("failed")

    with pytest.raises(Exception):
        runez.retry_run(failing_call, x=1, _tries=2)
    assert "failed, retrying" in logged.pop()