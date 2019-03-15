import os

import pytest

import runez


TEST_DIR = os.path.dirname(__file__)
SAMPLES = os.path.join(TEST_DIR, "sample")


def test_global_setup():
    assert str(runez.config.CONFIG) == "empty"
    assert len(runez.config.CONFIG.providers) == 0

    # Using a non-existent json source is a no-op
    runez.config.use_json("non-existent")
    assert len(runez.config.CONFIG.providers) == 0

    # Add one CLI source
    runez.config.use_cli(["a=b"])
    assert str(runez.config.CONFIG) == "--config: 1 values"
    assert len(runez.config.CONFIG.providers) == 1
    assert runez.config.get_str("a") == "b"

    # Add propsfs
    runez.config.use_propsfs()
    assert len(runez.config.CONFIG.providers) == 2
    assert runez.config.get_str("a") == "b"
    assert str(runez.config.CONFIG) == "--config: 1 values, propsfs"

    # Adding propsfs twice is a no-op
    runez.config.use_propsfs()
    assert len(runez.config.CONFIG.providers) == 2

    # Re-adding CLI with different values replaces prev
    runez.config.use_cli(["a=c"])
    assert str(runez.config.CONFIG) == "--config: 1 values, propsfs"
    assert len(runez.config.CONFIG.providers) == 2
    assert runez.config.get_str("a") == "c"

    # Add a json source
    runez.config.use_json(os.path.join(SAMPLES, "sample.json"))
    assert len(runez.config.CONFIG.providers) == 3
    assert runez.config.get_str("some-key") == "some-value"
    assert runez.config.get_int("some-int") == 51

    # Replace providers
    runez.config.set_providers(runez.config.DictProvider(None))
    assert str(runez.config.CONFIG) == "dict: 0 values"
    assert len(runez.config.CONFIG.providers) == 1

    # Remove all providers
    runez.config.clear()
    assert str(runez.config.CONFIG) == "empty"
    assert len(runez.config.CONFIG.providers) == 0


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
    assert runez.config.get_bytesize("foo", default="5", default_unit="k") == 5120
    assert runez.config.get_json("foo", default='["a"]') == ["a"]


def test_cli():
    config = runez.config.Configuration()

    config.use_cli(None)
    assert str(config) == "empty"

    config.use_cli(["foo", "", None, "a=b", "c=5.1k", " ", ""])
    assert str(config) == "--config: 3 values"
    assert config.get_str("foo") == ""
    assert config.get_str("a") == "b"
    assert config.get_str("c") == "5.1k"
    assert config.get_bytesize("c") == 5222

    assert config.get_str("not-there") is None
    assert config.get_str("") is None


def test_samples():
    config = runez.config.Configuration()
    config.add(runez.config.PropsfsProvider(SAMPLES))
    assert str(config) == "propsfs"

    assert config.get_str("non-existent") is None

    assert config.get_str("some-string") == "hello there"
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


def test_capped():
    assert runez.config.to_number(int, "123", minimum=200) == 200
    assert runez.config.to_number(int, "123", maximum=100) == 100
    assert runez.config.to_number(int, "123", minimum=100, maximum=200) == 123
    assert runez.config.to_number(int, "123", minimum=100, maximum=110) == 110


def test_numbers():
    assert runez.config.to_number(int, None) is None
    assert runez.config.to_number(int, "") is None
    assert runez.config.to_number(int, "foo") is None
    assert runez.config.to_number(int, "1foo") is None
    assert runez.config.to_number(int, "1.foo") is None

    assert runez.config.to_number(int, "123") == 123
    assert runez.config.to_number(int, "  123  ") == 123
    assert runez.config.to_number(int, "1.23") is None

    assert runez.config.to_number(float, "1.23") == 1.23
    assert runez.config.to_number(float, "  1.23  ") == 1.23
    assert runez.config.to_number(float, "1.2.3") is None


def test_boolean():
    assert runez.config.to_boolean(None) is False
    assert runez.config.to_boolean("") is False
    assert runez.config.to_boolean("t") is False
    assert runez.config.to_boolean("0") is False
    assert runez.config.to_boolean("0.0") is False
    assert runez.config.to_boolean("1.0.0") is False

    assert runez.config.to_boolean("True") is True
    assert runez.config.to_boolean("yes") is True
    assert runez.config.to_boolean("ON") is True
    assert runez.config.to_boolean("5") is True
    assert runez.config.to_boolean("16.1") is True


def test_bytesize():
    config = runez.config.Configuration(runez.config.PropsfsProvider(SAMPLES))
    # Override 'some-int' (no prefix, same key as from samples folder)
    config.use_cli(("some-int=12", "some-string=foo"))

    # Introduce 2 prefixed keys
    config.use_cli(("twenty-k=20kb", "five-one-g=5.1g"), prefix="test", name="prefixed")

    assert str(config) == "prefixed: 2 values, --config: 2 values, propsfs"

    # CLIs are added at front of list by default
    assert config.get_bytesize("some-int") == 12
    assert config.get_bytesize("some-int", default_unit="k") == 12 * 1024
    assert config.get_bytesize("some-int", default_unit="m") == 12 * 1024 * 1024

    assert config.get_bytesize("test.twenty-k") == 20 * 1024
    assert config.get_bytesize("test.five-one-g") == int(5.1 * 1024 * 1024 * 1024)

    assert config.get_bytesize("test.twenty-k", minimum=5, maximum=100) == 100

    # Invalid default unit affects only ints without unit
    assert config.get_bytesize("some-int", default_unit="a") is None
    assert config.get_bytesize("test.twenty-k", default_unit="a") == 20 * 1024

    assert config.get_bytesize("some-string") is None
    assert config.get_bytesize("some-string", default=5) == 5
    assert config.get_bytesize("some-string", default="5k") == 5 * 1024
    assert config.get_bytesize("some-string", default=5, default_unit="k") == 5 * 1024
    assert config.get_bytesize("some-string", default="5m", default_unit="k") == 5 * 1024 * 1024

    assert runez.config.to_bytesize(10) == 10
    assert runez.config.to_bytesize(None) is None
    assert runez.config.to_bytesize("") is None
    assert runez.config.to_bytesize("1a") is None

    assert runez.config.to_bytesize(10, default_unit="k", base=1024) == 10 * 1024
    assert runez.config.to_bytesize(10, default_unit="k", base=1000) == 10000
    assert runez.config.to_bytesize("10", default_unit="k", base=1000) == 10000
    assert runez.config.to_bytesize("10m", default_unit="k", base=1000) == 10000000

    with pytest.raises(ValueError):
        # Bogus default_unit
        runez.config.to_bytesize(10, default_unit="a", base=1000)


def test_to_dict():
    assert runez.to_dict(None) == {}
    assert runez.to_dict("") == {}

    assert runez.to_dict("a=b,pref.c=d") == {"a": "b", "pref.c": "d"}
    assert runez.to_dict("a=b,pref.c=d", prefix="pref") == {"pref.a": "b", "pref.c": "d"}

    assert runez.to_dict("a=b,pref.c=d", prefix="pref", separators=":+") == {"pref.a=b,pref.c=d": ""}
    assert runez.to_dict("a:b+pref.c:d", prefix="pref", separators=":+") == {"pref.a": "b", "pref.c": "d"}


def test_to_int():
    # bogus
    assert runez.to_int(None) is None
    assert runez.to_int(None, default=0) == 0
    assert runez.to_int("foo", default=1) == 1
    assert runez.to_int("6.1", default=2) == 2

    # valid
    assert runez.to_int(5, default=3) == 5
    assert runez.to_int("5", default=3) == 5


def test_props_front():
    # --config not at front of list, propsfs now takes precedence
    config = runez.config.Configuration(runez.config.PropsfsProvider(SAMPLES))
    config.use_cli(("some-int=12", "some-string=foo"), front=False)
    assert config.get_bytesize("some-int") == 123
    assert str(config) == "propsfs, --config: 2 values"


def test_json():
    assert runez.config.from_json(None) is None
    assert runez.config.from_json("") is None
    assert runez.config.from_json("foo") is None
    assert runez.config.from_json("{") is None
    assert runez.config.from_json(5) is None
    assert runez.config.from_json({}) is None
    assert runez.config.from_json([]) is None

    assert runez.config.from_json(' "foo" ') == "foo"
    assert runez.config.from_json("5") == 5

    assert runez.config.from_json("{}") == {}
    assert runez.config.from_json("[5, 6]") == [5, 6]
