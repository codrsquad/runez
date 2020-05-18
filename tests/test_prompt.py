import os

import pytest
from mock import patch

import runez
from runez.prompt import ask_once, interactive_prompt


def custom_serializer(value):
    if value == "invalid":
        return None

    return {"value": value}


def test_no_tty():
    v = ask_once("test", "Please enter value: ", fatal=False)
    assert v is None

    with pytest.raises(runez.system.AbortException):
        ask_once("test", "Please enter value: ")

    with pytest.raises(Exception):
        # pytest should raise an exception if trying to call input() from a test case
        interactive_prompt("test")


@patch("runez.prompt.is_tty", return_value=True)
@patch("runez.prompt.interactive_prompt", side_effect=str)
def test_with_tty(*_):
    with runez.TempFolder() as tmp:
        v = ask_once("test", "foo", serializer=custom_serializer, fatal=False, base=tmp)
        assert v == {"value": "foo"}

        # Verify that file was indeed stored
        path = os.path.join(tmp, "test.json")
        assert runez.read_json(path) == {"value": "foo"}

        # Verify that returned value is the 1st one stored
        v = ask_once("test", "bar", fatal=False, base=tmp)
        assert v == {"value": "foo"}

        # Verify that if `serializer` returns None, value is not returned/stored
        v = ask_once("test-invalid", "invalid", serializer=custom_serializer, fatal=False, base=tmp)
        assert v is None

        # Simulate CTRL+C
        with patch("runez.prompt.interactive_prompt", side_effect=KeyboardInterrupt):
            v = ask_once("test2", "test2", serializer=custom_serializer, fatal=False, base=tmp)
            assert v is None
