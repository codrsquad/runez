import logging

from mock import patch

import runez
from runez.serialize import same_type, type_name


def test_json(temp_folder):
    assert runez.read_json(None, fatal=False) is None
    assert runez.save_json(None, None, fatal=False) == 0

    data = {"a": "b"}

    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.save_json(data, "sample.json") == 1
        assert "Would save" in logged.pop()

    with runez.CaptureOutput() as logged:
        assert runez.read_json("sample.json", fatal=False) is None
        assert "No file" in logged.pop()

        assert runez.read_json("sample.json", default={}, fatal=False) == {}
        assert not logged

        with patch("runez.serialize.open", side_effect=Exception):
            assert runez.save_json(data, "sample.json", fatal=False) == -1
            assert "Couldn't save" in logged.pop()

        assert runez.save_json(data, "sample.json", logger=logging.debug) == 1
        assert "Saved " in logged.pop()

        with patch("io.open", side_effect=Exception):
            assert runez.read_json("sample.json", fatal=False) is None
            assert "Couldn't read" in logged.pop()

        assert runez.read_json("sample.json", logger=logging.debug) == data
        assert "Read " in logged.pop()

        assert runez.read_json("sample.json", default=[], fatal=False) == []
        assert "Wrong type" in logged.pop()

    with runez.CaptureOutput() as logged:
        # Try with an object that isn't directly serializable, but has a to_dict() function
        obj = runez.State()
        obj.to_dict = lambda *_: data

        assert runez.save_json(obj, "sample2.json", logger=logging.debug) == 1
        assert "Saved " in logged.pop()

        assert runez.read_json("sample2.json", logger=logging.debug) == data
        assert "Read " in logged.pop()


def test_types():
    assert type_name(None) == "None"
    assert type_name("some-string") == "str"
    assert type_name({}) == "dict"
    assert type_name([]) == "list"
    assert type_name(1) == "int"

    assert same_type(None, None)
    assert not same_type(None, "")
    assert same_type("some-string", "some-other-string")
    assert same_type("some-string", u"some-unicode")
    assert same_type(["some-string"], [u"some-unicode"])
    assert same_type(1, 2)


def test_serialization(logged):
    j = runez.Serializable()
    assert str(j) == "no source"
    j.save()  # no-op
    j.set_from_dict({}, source="test")
    j.some_list = []
    j.some_string = ""

    j.set_from_dict({"some_key": "bar", "some-list": "some-value", "some-string": "some-value"}, source="test")
    assert "some_key is not an attribute" in logged
    assert "Wrong type 'str' for Serializable.some_list in test, expecting 'list'" in logged.pop()

    assert str(j) == "test"
    assert not j.some_list
    assert not hasattr(j, "some_key")
    assert j.some_string == "some-value"
    assert j.to_dict() == {"some-list": [], "some-string": "some-value"}

    j.reset()
    assert not j.some_string

    j = runez.Serializable.from_json("")
    assert str(j) == "no source"

    j = runez.Serializable.from_json("/dev/null/not-there", fatal=False)
    assert str(j) == "/dev/null/not-there"
    j.save(fatal=False)
    assert "Couldn't save" in logged.pop()
