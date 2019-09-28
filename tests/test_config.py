from __future__ import print_function

import os

from mock import patch

import runez


TEST_DIR = os.path.dirname(__file__)
SAMPLES = os.path.join(TEST_DIR, "sample")


def test_no_implementation():
    provider = runez.config.ConfigProvider()
    assert str(provider) == "config"
    assert provider.overview() == "config"
    assert provider.get("anything") is None


def test_global_setup():
    assert str(runez.config.CONFIG) == "empty"
    assert len(runez.config.CONFIG.providers) == 0

    # Using a non-existent json source is a no-op
    runez.config.use_json("non-existent")
    assert len(runez.config.CONFIG.providers) == 0

    # Add one CLI source
    runez.config.use_cli(["a=b"])
    assert str(runez.config.CONFIG) == "--config"
    assert len(runez.config.CONFIG.providers) == 1
    assert runez.config.get_str("a") == "b"

    # Add propsfs
    runez.config.use_propsfs()
    assert len(runez.config.CONFIG.providers) == 2
    assert runez.config.get_str("a") == "b"
    assert str(runez.config.CONFIG) == "--config, propsfs"

    # Adding propsfs twice is a no-op
    runez.config.use_propsfs()
    assert len(runez.config.CONFIG.providers) == 2

    # Re-adding CLI with different values replaces prev
    runez.config.use_cli(["a=c"])
    assert str(runez.config.CONFIG) == "--config, propsfs"
    assert len(runez.config.CONFIG.providers) == 2
    assert runez.config.get_str("a") == "c"

    # Add a json source
    runez.config.use_json(os.path.join(SAMPLES, "sample.json"))
    assert len(runez.config.CONFIG.providers) == 3
    assert runez.config.get_str("some-key") == "some-value"
    assert runez.config.get_int("some-int") == 51

    # Replace providers
    runez.config.set_providers(runez.config.DictProvider(None))
    assert str(runez.config.CONFIG) == "dict"
    assert len(runez.config.CONFIG.providers) == 1

    # Remove all providers
    runez.config.clear()
    assert str(runez.config.CONFIG) == "empty"
    assert len(runez.config.CONFIG.providers) == 0

    # Custom dict
    runez.config.set_providers(runez.config.DictProvider({"a": {"b": "c"}}))
    assert str(runez.config.CONFIG) == "dict"
    assert len(runez.config.CONFIG.providers) == 1
    assert runez.config.get("a") == {"b": "c"}
    assert runez.config.get_str("a") == str({"b": "c"})


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
    assert str(config) == "--config"
    assert config.get_str("foo") == ""
    assert config.get_str("a") == "b"
    assert config.get_str("c") == "5.1k"
    assert config.get_bytesize("c") == 5222

    assert config.get_str("not-there") is None
    assert config.get_str("") is None


def test_env_vars():
    with runez.CaptureOutput() as output:
        with patch.dict(os.environ, {"SOME_KEY": "some-value"}, clear=True):
            config = runez.config.Configuration()
            config.tracer = print
            config.use_env_vars()
            assert len(config.providers) == 1
            assert len(config.providers[0].values) == 1
            assert str(config) == "env vars"
            assert config.get_str("SOME_KEY") == "some-value"
            assert config.get_str("some-key") == "some-value"
            assert "Adding config provider env vars" in output.pop()

            assert config.get_str("key") is None
            assert not output

            # Using same provider twice yields to same outcome
            config.use_env_vars()
            assert "Replacing config provider env vars at index 0" in output.pop()
            assert len(config.providers) == 1
            assert str(config) == "env vars"
            assert config.get_str("SOME_KEY") == "some-value"
            assert config.get_str("some-key") == "some-value"
            assert "Using some-key='some-value' from env vars" in output.pop()

            # Different view on env vars taken into account
            config.use_env_vars(prefix="SOME_")
            assert "Adding config provider SOME_* env vars to front" in output.pop()
            assert len(config.providers) == 2
            assert config.overview() == "SOME_* env vars: 1 values, env vars: 1 values"
            assert config.get_str("some-key") == "some-value"
            output.clear()
            assert config.get_str("key") == "some-value"
            assert "Using key='some-value' from SOME_* env vars" in output.pop()

            # Again, adding same provider twice is a no-op
            config.use_env_vars(prefix="SOME_")
            assert "Replacing config provider SOME_* env vars at index 0" in output.pop()
            assert len(config.providers) == 2

        with patch.dict(os.environ, {"FOO": "1", "MY_FOO": "2", "MY_FOO_X": "3"}, clear=True):
            config = runez.config.Configuration()
            config.use_env_vars(prefix="MY_", suffix="_X", name="prog")
            assert str(config) == "prog"
            assert config.get_str("FOO") == "3"
            assert config.get_str("MY_FOO_X") == "3"
            assert config.get_str("foo") == "3"
            assert config.get_str("my-foo") == "3"
            assert config.get_str("my-foo-x") == "3"


def test_samples():
    with runez.CaptureOutput() as output:
        config = runez.config.Configuration()
        config.tracer = print
        config.add(runez.config.PropsfsProvider(SAMPLES))
        assert str(config) == "propsfs"
        assert "Adding config provider propsfs" in output.pop()

        assert config.get_str("non-existent") is None
        assert not output

        assert config.get_str("some-string") == "hello there"
        assert "Using some-string='hello there' from propsfs" in output.pop()

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


def test_boolean():
    assert runez.config.parsed_boolean(None) is False
    assert runez.config.parsed_boolean("") is False
    assert runez.config.parsed_boolean("t") is False
    assert runez.config.parsed_boolean("0") is False
    assert runez.config.parsed_boolean("0.0") is False
    assert runez.config.parsed_boolean("1.0.0") is False

    assert runez.config.parsed_boolean("True") is True
    assert runez.config.parsed_boolean("Y") is True
    assert runez.config.parsed_boolean("yes") is True
    assert runez.config.parsed_boolean("On") is True
    assert runez.config.parsed_boolean("5") is True
    assert runez.config.parsed_boolean("16.1") is True


def test_bytesize():
    config = runez.config.Configuration(runez.config.PropsfsProvider(SAMPLES))
    # Override 'some-int' (no prefix, same key as from samples folder)
    config.use_cli(("some-int=12", "some-string=foo"))

    # Introduce 2 prefixed keys
    config.use_cli(("twenty-k=20kb", "five-one-g=5.1g"), prefix="test", name="prefixed")

    assert str(config) == "prefixed, --config, propsfs"
    assert config.overview() == "prefixed: 2 values, --config: 2 values, propsfs: %s" % SAMPLES

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

    assert runez.config.parsed_bytesize(10) == 10
    assert runez.config.parsed_bytesize(None) is None
    assert runez.config.parsed_bytesize("") is None
    assert runez.config.parsed_bytesize("1a") is None

    assert runez.config.parsed_bytesize(10, default_unit="k", base=1024) == 10 * 1024
    assert runez.config.parsed_bytesize(10, default_unit="k", base=1000) == 10000
    assert runez.config.parsed_bytesize("10", default_unit="k", base=1000) == 10000
    assert runez.config.parsed_bytesize("10m", default_unit="k", base=1000) == 10000000

    assert runez.config.parsed_bytesize(10, default_unit="a", base=1000) is None  # Bogus default_unit


def test_parsed_dict():
    assert runez.config.parsed_dict(None) == {}
    assert runez.config.parsed_dict("") == {}

    assert runez.config.parsed_dict("a=b,pref.c=d") == {"a": "b", "pref.c": "d"}
    assert runez.config.parsed_dict("a=b,pref.c=d", prefix="pref") == {"pref.a": "b", "pref.c": "d"}

    assert runez.config.parsed_dict("a=b,pref.c=d", prefix="pref", separators=":+") == {"pref.a=b,pref.c=d": ""}
    assert runez.config.parsed_dict("a:b+pref.c:d", prefix="pref", separators=":+") == {"pref.a": "b", "pref.c": "d"}


def test_props_front():
    # --config not at front of list, propsfs now takes precedence
    config = runez.config.Configuration(runez.config.PropsfsProvider(SAMPLES))
    config.use_cli(("some-int=12", "some-string=foo"), front=False)
    assert config.get_bytesize("some-int") == 123
    assert str(config) == "propsfs, --config"


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
