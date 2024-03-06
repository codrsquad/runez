import os

import pytest

import runez

SAMPLES = runez.DEV.tests_path("sample")


def test_missing():
    assert runez.config.get_str(None) is None
    assert runez.config.get_str("") is None
    assert runez.config.get_str("foo") is None
    assert runez.config.get_int("foo") is None
    assert runez.config.get_float("foo") is None
    assert runez.config.get_bool("foo") is None
    assert runez.config.get_bytesize("foo") is None
    assert runez.config.get_json("foo") is None

    assert runez.config.get_str("foo", default="bar") == "bar"
    assert runez.config.get_int("foo", default=5) == 5
    assert runez.config.get_float("foo", default=5) == 5
    assert runez.config.get_bool("foo", default=True) is True
    assert runez.config.get_bool("foo", default=False) is False
    assert runez.config.get_bytesize("foo", default=5) == 5
    assert runez.config.get_bytesize("foo", default="5k") == 5120
    assert runez.config.get_bytesize("foo", default="5K") == 5120
    assert runez.config.get_bytesize("foo", default="5", default_unit="k") == 5120
    assert runez.config.get_json("foo", default='["a"]') == ["a"]


def test_no_implementation():
    base = runez.config.ConfigProvider()
    assert base.values is None

    config = runez.config.Configuration(providers=[runez.config.ConfigProvider()])
    assert str(config) == "config"
    assert config.overview() == "config: 0 values"
    assert config.get("anything") is None

    config.set_providers(runez.config.ConfigProvider())
    assert str(config) == "config"
    assert config.get("anything") is None

    config.use_json(os.path.join(SAMPLES, "sample.json"))
    assert config.get_int("some-int") == 51

    config.set_providers()
    assert str(config) == "empty"
    assert config.get("anything") is None

    with pytest.raises(TypeError, match="Invalid config provider"):
        config.add(object())

    assert str(config) == "empty"


def test_samples(temp_log):
    runez.log.setup()
    runez.log.enable_trace(True)
    config = runez.config.Configuration()
    config.add(runez.config.PropsfsProvider(SAMPLES))
    assert str(config) == "propsfs"
    assert "Adding config provider propsfs" in temp_log.tracked.pop()

    assert config.get_str("non-existent") is None
    assert not temp_log.tracked

    assert config.get_str("some-string") == "hello there"
    assert "Using some-string='hello there' from propsfs" in temp_log.tracked.pop()

    assert config.get_int("some-string") is None
    assert config.get_float("some-string") is None
    assert config.get_bool("some-string") is False
    assert config.get_bytesize("some-string") is None

    assert config.get_str("some-string", default="foo") == "hello there"
    assert config.get_int("some-string", default=5) == 5
    assert config.get_float("some-string", default=5.1) == 5.1
    assert config.get_bool("some-string", default=False) is False
    assert config.get_bytesize("some-string", default=5) == 5

    assert config.get_str("some-int") == "123"
    assert config.get_int("some-int") == 123
    assert config.get_float("some-int") == 123
    assert config.get_bool("some-int") is True
    assert config.get_bytesize("some-int") == 123

    assert config.get_json("sample.json") == {"some-key": "some-value", "some-int": 51}
    assert config.get_json("some-string") is None
    assert config.get_json("some-string", default={"a": "b"}) == {"a": "b"}
    assert config.get_json("some-string", default='{"a": "b"}') == {"a": "b"}

    additional = runez.config.DictProvider({"some-string": "foo", "x": "y"})
    config.add(additional, front=True)

    values = config.values
    assert len(values) == 4
    assert values["sample.json"]
    assert values["some-int"] == "123"
    assert values["some-string"] == "foo"
    assert values["x"] == "y"
