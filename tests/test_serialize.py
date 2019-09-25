import datetime
import logging

import pytest
from mock import patch

import runez
from runez.serialize import same_type, type_name


class SomeRecord(object):

    name = "my record"
    some_int = 5


class SomeSerializable(runez.Serializable):

    name = "my name"
    some_int = 7
    some_value = None

    def set_some_int(self, value):
        self.some_int = value


def test_equality():
    data = {"name": "some name", "some_int": 15}
    obj = SomeSerializable.from_dict(data)
    obj2 = SomeSerializable()
    assert obj != obj2

    obj2.name = "some name"
    obj2.some_int = 15
    assert obj == obj2

    assert len(runez.attributes(SomeSerializable)) == 3
    assert len(runez.attributes(obj)) == 3
    assert len(runez.attributes(obj2)) == 3


def test_json(temp_folder):
    assert runez.read_json(None, fatal=False) is None

    assert runez.represented_json(None) == "null\n"
    assert runez.represented_json([]) == "[]\n"
    assert runez.represented_json({}) == "{}\n"
    assert runez.represented_json("foo") == '"foo"\n'

    assert runez.save_json(None, None, fatal=False) == 0

    data = {"a": "b"}

    assert not runez.DRYRUN
    with runez.CaptureOutput(dryrun=True) as logged:
        assert runez.save_json(data, "sample.json") == 1
        assert "Would save" in logged.pop()
    assert not runez.DRYRUN

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
        obj = SomeRecord()
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
    obj = runez.Serializable()
    assert str(obj) == "no source"
    assert runez.attributes(obj) is None

    obj.save()  # no-op
    obj.set_from_dict({}, source="test")  # no-op

    with pytest.raises(TypeError):
        obj.set_from_dict({"some_key": "bar"})

    obj = SomeSerializable()
    obj.set_from_dict({"some_key": "bar", "name": 1, "some_value": ["foo"]}, source="test")
    assert "some_key is not an attribute" in logged
    assert "Wrong type 'int' for SomeSerializable.name in test, expecting 'str'" in logged.pop()

    assert str(obj) == "test"
    assert not hasattr(obj, "some_key")
    assert obj.name == "my name"
    assert obj.to_dict() == {"name": "my name", "some_int": 7, "some_value": ["foo"]}

    obj2 = SomeSerializable.from_json("")
    assert str(obj2) == "no source"
    assert obj != obj2

    obj.reset()
    assert obj.name == ""
    assert obj.some_int == 0
    assert obj.some_value is None
    assert obj == obj2

    obj3 = SomeSerializable.from_json("/dev/null/not-there", fatal=False)
    assert obj == obj3
    assert str(obj3) == "/dev/null/not-there"
    obj3.save(fatal=False)
    assert "Couldn't save" in logged.pop()


def test_sanitize():
    assert runez.json_sanitized(None) is None
    assert runez.json_sanitized({1, 2}) == [1, 2]

    now = datetime.datetime.now()
    assert runez.json_sanitized(now) == str(now)
    assert runez.json_sanitized(now, dt=None) is now
    assert runez.json_sanitized([now]) == [str(now)]
    assert runez.json_sanitized([now], dt=None) == [now]

    obj = object()
    assert runez.json_sanitized(obj) == str(obj)
    assert runez.json_sanitized(obj, stringify=None) is obj
