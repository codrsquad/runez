import math

import runez


def test_boolean():
    assert runez.to_boolean(None) is False
    assert runez.to_boolean("") is False
    assert runez.to_boolean("t") is False
    assert runez.to_boolean("0") is False
    assert runez.to_boolean("0.0") is False
    assert runez.to_boolean("1.0.0") is False

    assert runez.to_boolean("True") is True
    assert runez.to_boolean("Y") is True
    assert runez.to_boolean("yes") is True
    assert runez.to_boolean("On") is True
    assert runez.to_boolean("5") is True
    assert runez.to_boolean("0.1") is True
    assert runez.to_boolean("16.1") is True


def test_bytesize():
    assert runez.to_bytesize(10) == 10
    assert runez.to_bytesize(None) is None
    assert runez.to_bytesize("") is None
    assert runez.to_bytesize("1a") is None

    assert runez.to_bytesize("10") == 10
    assert runez.to_bytesize("10.4") == 10
    assert runez.to_bytesize("10.6") == 11
    assert runez.to_bytesize(10, default_unit="k", base=1024) == 10 * 1024
    assert runez.to_bytesize(10, default_unit="k", base=1000) == 10000
    assert runez.to_bytesize("10", default_unit="k", base=1000) == 10000
    assert runez.to_bytesize("10m", default_unit="k", base=1000) == 10000000
    assert runez.to_bytesize("10.m", default_unit="k", base=1000) == 10000000
    assert runez.to_bytesize("10.4m", default_unit="k", base=1000) == 10400000

    assert runez.to_bytesize(10, default_unit="a", base=1000) is None  # Bogus default_unit


def test_plural():
    assert runez.plural(None) == "no values"
    assert runez.plural(None, None) == "no values"
    assert runez.plural("chair") == "chairs"
    assert runez.plural(None, "walker") == "no walkers"

    assert runez.plural(None) == "no values"
    assert runez.plural(1) == "1 value"
    assert runez.plural("foo", "character") == "3 characters"

    assert runez.plural(2, "match") == "2 matches"
    assert runez.plural(0, "dish") == "0 dishes"
    assert runez.plural(5, "goth") == "5 goths"
    assert runez.plural(7, "diff") == "7 diffs"

    assert runez.plural(1, "penny") == "1 penny"
    assert runez.plural(2, "penny") == "2 pennies"

    assert runez.plural([], "record") == "0 records"
    assert runez.plural([""], "record") == "1 record"

    assert runez.plural(1, "person") == "1 person"
    assert runez.plural(2, "person") == "2 people"

    assert runez.plural(2, "man") == "2 men"
    assert runez.plural(2, "woman") == "2 women"
    assert runez.plural(2, "status") == "2 statuses"

    assert runez.plural(0, "carrot") == "0 carrots"
    assert runez.plural(1, "carrot") == "1 carrot"
    assert runez.plural(20, "carrot") == "20 carrots"
    assert runez.plural(20000, "carrot") == "20K carrots"
    assert runez.plural(20000, "carrot", base=None) == "20K carrots"
    assert runez.plural(20000, "carrot", base=0) == "20000 carrots"


def test_representation():
    assert runez.represented_bytesize(20) == "20 B"
    assert runez.represented_bytesize(20, unit="") == "20"
    assert runez.represented_bytesize(9000) == "8.8 KB"
    assert runez.represented_bytesize(20000) == "20 KB"
    assert runez.represented_bytesize(20000, unit="") == "20 K"
    assert runez.represented_bytesize(20000000) == "19 MB"
    assert runez.represented_bytesize(20000000000) == "19 GB"
    assert runez.represented_bytesize(20000000000000) == "18 TB"
    assert runez.represented_bytesize(20000000000000000) == "18 PB"
    assert runez.represented_bytesize(20000000000000000000) == "17764 PB"

    assert runez.represented_with_units(20) == "20"
    assert runez.represented_with_units(999.9) == "999.9"
    assert runez.represented_with_units(1001) == "1K"
    assert runez.represented_with_units(1060) == "1.1K"
    assert runez.represented_with_units(8900) == "8.9K"
    assert runez.represented_with_units(20304050600000000000) == "20304P"


SAMPLE_TABULATED_OUTPUT = """
  UID   PID  PPID   C STIME   TTY           TIME CMD
  501 96590    42   0 foo bar ttys009    0:04.60 -bash
  502     4     5   0         ttys009            zsh
--
  UID   PID  PPID   C STIME   TTY           TIME CMD
  501 96590    42   0 18Dec20 ttys009    0:04.60 -bash --login
--
UID        PID  PPID  C STIME TTY      STAT   TIME CMD
zoran        7    42  0 15:23 tty1     S      0:00 /bin/bash --login
--
"""


def tabulated_samples():
    lines = []
    for line in SAMPLE_TABULATED_OUTPUT.splitlines():
        if not line or line.startswith("#"):
            continue

        if line.startswith("--"):
            yield len(lines) - 1, "\n".join(lines)
            lines = []
            continue

        lines.append(line)

    if lines:
        yield len(lines) - 1, "\n".join(lines)


def test_tabulated_parsing():
    assert runez.parsed_tabular("  \nfoo") == []  # First line must have a header...

    for expected, output in tabulated_samples():
        parsed = list(runez.parsed_tabular(output))
        assert len(parsed) == expected
        assert "bash" in parsed[0]["CMD"]


DOCKER_PS_SAMPLE = """
CONTAINER_ID  IMAGE                  COMMAND  CREATED         STATUS         PORTS                   NAMES
d7907cca5247  foo/bar:stable         "/init"  18 minutes ago  Up 18 minutes                          foo
6bda1a6f83eb  linuxserver/syncthing  "/init"  7 days ago      Up 43 hours    0.0.0.0:123->123/tcp    syncthing
"""


def test_tabulated_docker_ps():
    info = runez.parsed_tabular(DOCKER_PS_SAMPLE.strip())
    assert info == [
        {
            "CONTAINER_ID": "d7907cca5247",
            "IMAGE": "foo/bar:stable",
            "COMMAND": '"/init"',
            "CREATED": "18 minutes ago",
            "STATUS": "Up 18 minutes",
            "NAMES": "foo",
        },
        {
            "CONTAINER_ID": "6bda1a6f83eb",
            "IMAGE": "linuxserver/syncthing",
            "COMMAND": '"/init"',
            "CREATED": "7 days ago",
            "STATUS": "Up 43 hours",
            "PORTS": "0.0.0.0:123->123/tcp",
            "NAMES": "syncthing",
        },
    ]


def test_to_float():
    assert runez.to_float(None) is None
    assert runez.to_float("foo") is None
    assert runez.to_float("-.if") is None
    assert runez.to_float(["foo"], lenient=True) is None

    assert runez.to_float("0") == 0.0
    assert runez.to_float("-5") == -5.0
    assert runez.to_float("15") == 15.0
    assert runez.to_float("+135.057E+4") == 1350570.0
    assert runez.to_float("-135000.5e-3") == -135.0005

    assert math.isnan(runez.to_float("nan"))
    assert math.isinf(runez.to_float("inf"))
    assert math.isinf(runez.to_float(".inf"))
    assert math.isinf(runez.to_float("-.inf"))

    assert isinstance(runez.to_float("15"), float)
    assert isinstance(runez.to_float("15", lenient=True), int)


def test_to_int():
    assert runez.to_int(None) is None
    assert runez.to_int("foo") is None
    assert runez.to_int(["foo"]) is None
    assert runez.to_int("5.0") is None
    assert runez.to_int("_5_") is None
    assert runez.to_int("_5") is None
    assert runez.to_int("5_") is None
    assert runez.to_int("1__5") is None
    assert runez.to_int("1_ 5") is None

    assert runez.to_int("0") == 0
    assert runez.to_int("-5") == -5
    assert runez.to_int("15") == 15

    assert runez.to_int("0o10") == 8
    assert runez.to_int("0x10") == 16
    assert runez.to_int("0o1_0") == 8
    assert runez.to_int("0x1_0") == 16

    assert runez.to_int(" 1_500 ") == 1500
    assert runez.to_int("1_5 ") == 15
    assert runez.to_int("1_500_001 ") == 1500001


def test_wordification():
    assert runez.identifiers(None) == []
    assert runez.identifiers("") == []
    assert runez.identifiers("a_b1") == ["a_b1"]
    assert runez.identifiers("hi_There-you") == ["hi_There", "you"]
    assert runez.identifiers(["a", ["b_c(d)", None, [1]]]) == ["a", "b_c", "d", "1"]
    assert runez.identifiers({"a": "b_c(d)"}) == ["a", "b_c", "d"]

    assert runez.words(None) == []
    assert runez.words("") == []
    assert runez.words("*") == []
    assert runez.words("a") == ["a"]
    assert runez.words("a b") == ["a", "b"]
    assert runez.words("a,b(c)") == ["a", "b", "c"]
    assert runez.words("a,,b") == ["a", "b"]
    assert runez.words("a_b1") == ["a", "b1"]
    assert runez.words("hi_There-you", normalize=str.lower) == ["hi", "there", "you"]
    assert runez.words({"a": "b_c(d)"}) == ["a", "b", "c", "d"]

    # Test de-camelization
    assert runez.words("foo", decamel=True) == ["foo"]
    assert runez.words("fooBar", decamel=True) == ["foo", "Bar"]
    assert runez.words("FooBar", decamel=True) == ["Foo", "Bar"]
    assert runez.words("_FooBar_", decamel=True, normalize=str.lower) == ["foo", "bar"]
    assert runez.words("someCamel_likeWords-FooBar_baz", decamel=True) == ["some", "Camel", "like", "Words", "Foo", "Bar", "baz"]

    assert runez.words(["a", "b_c", "a"]) == ["a", "b", "c", "a"]
    assert runez.words(["a", None, "b", 1]) == ["a", "b", "1"]
    assert runez.words(["a", [None, "b,c"], 1]) == ["a", "b", "c", "1"]

    assert runez.wordified(None) is None
    assert runez.wordified("Hello_There", delimiter="-") == "Hello-There"

    assert runez.snakified("my-key") == "MY_KEY"
    assert runez.camel_cased("my-key") == "MyKey"
    assert runez.entitled("my-key") == "My key"

    assert runez.affixed(None) is None
    assert runez.affixed("") == ""
    assert runez.affixed("", prefix="my-") == "my-"

    assert runez.affixed("my-key") == "my-key"
    assert runez.affixed("my-key", prefix="my-") == "my-key"
    assert runez.affixed("key", prefix="my-") == "my-key"
    assert runez.affixed("my-key", prefix="X_", normalize=runez.snakified) == "X_MY_KEY"
    assert runez.affixed("my-key", prefix="X_", suffix="+foo") == "X_my-key+foo"
