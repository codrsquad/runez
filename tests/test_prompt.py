import os

import pytest

import runez
from runez.conftest import verify_abort
from runez.prompt import ask_once, interactive_prompt


def custom_serializer(value):
    if value == "invalid":
        return None

    return {"value": value}


def test_no_tty():
    assert ask_once("test", "Please enter value: ", default=None) is None

    with pytest.raises(runez.system.AbortException):
        ask_once("test", "Please enter value: ")

    with pytest.raises(Exception):
        # pytest should raise an exception if trying to call input() from a test case
        interactive_prompt("test")


def test_with_tty(monkeypatch):
    monkeypatch.setattr(runez.prompt, "interactive_prompt", lambda x: str(x))
    expected = {"value": "foo"}
    runez.TERMINAL_INFO.is_stdout_tty = True
    with runez.TempFolder() as tmp:
        assert ask_once("test", "foo", serializer=custom_serializer, base=tmp) == expected

        assert runez.read_json("test.json") == expected
        assert ask_once("test", "bar", base=tmp) == expected  # Ask a 2nd time, same response

        # Verify that if `serializer` returns None, value is not returned/stored
        response = verify_abort(ask_once, "test-invalid", "invalid", serializer=custom_serializer, base=tmp)
        assert "Invalid value provided" in response
        assert not os.path.exists("test-invalid.json")

        # Same, but don't raise exception (returns default)
        assert ask_once("test-invalid", "invalid", serializer=custom_serializer, default=None, base=tmp) is None

        # Simulate no value provided
        response = verify_abort(ask_once, "test-invalid", "", serializer=custom_serializer, base=tmp)
        assert "No value provided" in response

        # Simulate CTRL+C
        runez.conftest.patch_raise(monkeypatch, runez.prompt, "interactive_prompt", KeyboardInterrupt)
        response = verify_abort(ask_once, "test2", "test2", serializer=custom_serializer, base=tmp)
        assert "Cancelled by user" in response

    runez.TERMINAL_INFO.is_stdout_tty = False
