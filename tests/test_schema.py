import datetime
import logging

import runez
from runez.schema import Any, Boolean, Date, Datetime, Dict, Enum, Float, Integer, List, String, Struct, UniqueIdentifier
from runez.serialize import Serializable, SerializableDescendants, with_behavior


def test_any():
    a = Any()
    assert a.problem(None) is None
    assert a.problem("a") is None
    assert a.problem(4) is None
    assert a.problem([1, 2]) is None
    assert a.problem(object()) is None


def test_boolean():
    b = Boolean()
    assert b.problem(None) is None
    assert b.problem("a") is None
    assert b.problem(4) is None
    assert b.problem([1, 2]) is None
    assert b.problem(object()) is None

    assert b.converted(None) is None

    assert b.converted(True) is True
    assert b.converted(False) is False

    assert b.converted("a") is False
    assert b.converted("False") is False
    assert b.converted("true") is True
    assert b.converted("Y") is True
    assert b.converted("yes") is True

    assert b.converted(0) is False
    assert b.converted(4) is True
    assert b.converted(123.4) is True
    assert b.converted("123.4") is True
    assert b.converted("123.4a") is False

    assert b.converted([]) is False
    assert b.converted({}) is False
    assert b.converted([1, 2]) is True
    assert b.converted({"a": "b"}) is True

    assert b.converted(object()) is True


def test_date():
    dd = Date()
    assert str(dd) == "Date"
    assert dd.problem(None) is None
    assert dd.problem({}) == "expecting date, got '{}'"
    assert dd.converted(0) == datetime.date(1970, 1, 1)
    assert dd.converted("2019-09-02") == datetime.date(2019, 9, 2)
    assert dd.converted("2019-09-02 01:02:03") == datetime.date(2019, 9, 2)

    dd = Datetime()
    assert str(dd) == "Datetime"
    assert dd.problem(None) is None
    assert dd.problem({}) == "expecting datetime, got '{}'"
    assert dd.converted(0) == datetime.datetime(1970, 1, 1, tzinfo=runez.date.UTC)
    assert dd.converted("2019-09-02") == datetime.datetime(2019, 9, 2, tzinfo=runez.date.UTC)
    assert dd.converted("2019-09-02 01:02:03") == datetime.datetime(2019, 9, 2, 1, 2, 3, tzinfo=runez.date.UTC)


def test_dict():
    dd = Dict()
    assert str(dd) == "Dict[Any, Any]"
    assert dd.problem({}) is None
    assert dd.problem({1: "a"}) is None
    assert dd.problem({"a": 1}) is None

    dd = Dict(String)
    assert str(dd) == "Dict[String, Any]"
    assert dd.problem({}) is None
    assert dd.problem({1: "a"}) == "key: expecting string, got '1'"
    assert dd.problem({"a": 1}) is None

    dd = Dict(String, Integer)
    assert str(dd) == "Dict[String, Integer]"
    assert dd.problem(5) == "expecting dict, got '5'"
    assert dd.problem({}) is None
    assert dd.problem({1: "a"}) == "key: expecting string, got '1'"
    assert dd.problem({"a": "b"}) == "value: expecting int, got 'b'"
    assert dd.problem({"a": 1}) is None

    assert dd.converted({"a": 1}) == {"a": 1}
    assert dd.converted({"a": "1"}) == {"a": 1}

    dd = Dict(String, List(Integer))
    assert str(dd) == "Dict[String, List[Integer]]"
    assert dd.problem({}) is None
    assert dd.problem({"a": "b"}) == "value: expecting list, got 'b'"
    assert dd.problem({"a": ["1"]}) is None
    assert dd.problem({"a": ["b"]}) == "value: expecting int, got 'b'"


def test_enum():
    ee = Enum("foo bar")
    assert str(ee) == "Enum[bar, foo]"
    assert ee.problem(None) is None
    assert ee.problem("foo") is None
    assert ee.problem("x") == "'x' is not one of Enum[bar, foo]"
    assert ee.problem(1) == "'1' is not one of Enum[bar, foo]"


def test_list():
    ll = List()
    assert str(ll) == "List[Any]"
    assert ll.problem([]) is None
    assert ll.problem(["a"]) is None
    assert ll.problem([1, 2]) is None
    assert ll.problem({1, "2"}) is None

    assert ll.converted([1, "2"]) == [1, "2"]

    ll = List(Integer)
    assert str(ll) == "List[Integer]"
    assert ll.problem([]) is None
    assert ll.problem(["a"]) == "expecting int, got 'a'"
    assert ll.problem([1, 2]) is None
    assert ll.problem((1, 2)) is None
    assert ll.problem({1, "2"}) is None

    assert ll.converted([1, "2"]) == [1, 2]
    assert ll.converted((1, 2)) == [1, 2]
    assert sorted(ll.converted({1, "2"})) == [1, 2]


def test_number():
    ff = Float()
    assert str(ff) == "Float"
    assert ff.problem(None) is None
    assert ff.problem(5) is None
    assert ff.problem(5.3) is None
    assert ff.problem("foo") == "expecting float, got 'foo'"
    assert ff.problem([]) == "expecting float, got '[]'"

    assert ff.converted("5.4") == 5.4
    assert ff.converted(5) == 5.0
    assert ff.converted("0o10") == 8.0


class Car(Serializable, with_behavior(extras=(logging.info, "foo bar"))):
    make = String
    serial = UniqueIdentifier
    year = Integer

    def __init__(self, make=None, serial=None, year=None):
        self.make = make
        self.serial = serial
        self.year = year


class Hat(Struct):
    size = Integer(default=1)


class SpecializedCar(Car):
    """Used to test that ._meta.behavior is passed on properly to descendants"""

    hats = List(Hat)  # Test list of serializables


class Person(Serializable, with_behavior(strict=logging.error, hook=logging.info)):
    age = Date
    fingerprint = UniqueIdentifier(Integer)
    name = String(default="joe")

    car = Car
    hat = Hat

    def __init__(self, name=None):
        self.name = name


class GPerson(Person):
    """Used to test that ._meta.behavior is passed on properly to descendants"""

    age = Integer  # Change type on purpose
    group = Integer


def test_serializable(logged):
    assert len(list(SerializableDescendants.children(Car))) == 2
    assert len(list(SerializableDescendants.children(Person))) == 2
    assert len(list(SerializableDescendants.children(SpecializedCar))) == 1

    assert str(Serializable._meta.behavior) == "lenient"

    assert str(Car._meta.behavior) == "extras: function 'info', ignored extras: [foo, bar]"
    assert str(SpecializedCar._meta.behavior) == "extras: function 'debug'"  # extras are NOT inherited
    assert Car._meta.attributes_by_type(String) == ["make", "serial"]
    assert Car._meta.attributes_by_type(Integer) == ["year"]
    assert SpecializedCar._meta.attributes_by_type(Integer) == ["year"]
    assert SpecializedCar._meta.attributes_by_type(List) == ["hats"]

    assert str(Person._meta) == "Person (5 attributes, 0 properties)"
    assert str(Person._meta.behavior) == "strict: function 'error', extras: function 'debug', hook: function 'info'"
    # `hook` is inherited
    assert str(GPerson._meta.behavior) == "strict: function 'error', extras: function 'debug', hook: function 'info'"

    # Verify that most specific type wins (GPerson -> age)
    assert Person._meta.attributes_by_type(Integer) == ["fingerprint"]
    assert Person._meta.attributes_by_type(Date) == ["age"]
    assert GPerson._meta.attributes_by_type(Integer) == ["age", "fingerprint", "group"]
    assert GPerson._meta.attributes_by_type(Date) is None

    car = Car(year=2020)
    assert car.to_dict() == {"year": 2020}

    car = Car.from_dict({"foo": 1, "baz": 2, "serial": "bar"})
    assert car.serial == "bar"
    assert "foo" not in logged
    assert "Extra content given for Car: baz" in logged.pop()
    assert car.to_dict() == {"serial": "bar"}

    pp = Person()
    assert pp.age is None
    assert pp.fingerprint is None
    assert pp.name is None  # overridden by Person.__init__()
    assert pp.car is None
    assert pp.to_dict() == {}

    pp = Person.from_dict({"car": "foo", "fingerprint": "foo"})
    assert pp.fingerprint == "foo"  # Bogus value still used because 'strict' setting does not raise an exception
    assert "Can't deserialize Person.car: expecting compliant dict, got 'foo'" in logged
    assert "Can't deserialize Person.fingerprint: expecting int, got 'foo'" in logged.pop()

    Person.from_dict({"hat": {"size": "foo"}})
    assert "Can't deserialize Person.hat: expecting int, got 'foo'" in logged.pop()

    pp = Person.from_dict({"age": "2019-01-01", "car": {"make": "Honda", "year": 2010}, "fingerprint": 5})
    assert pp.age.year == 2019
    assert pp.car.make == "Honda"
    assert pp.car.year == 2010
    assert pp.fingerprint == 5
    assert pp.hat is None
    assert pp.to_dict() == {"age": "2019-01-01", "car": {"make": "Honda", "year": 2010}, "fingerprint": 5, "name": "joe"}

    # Default `name` from schema is respected, because we didn't call Person.__init__() explicitly
    pp = Person.from_dict({"age": 1567296012, "hat": {"size": "5"}})
    assert pp.age.year == 2019
    assert pp.hat.size == 5
    assert pp.to_dict() == {"age": "2019-09-01", "name": "joe", "hat": {"size": 5}}

    Person.from_dict({"car": {"make": "Honda", "foo": "bar"}})
    assert "'foo' is not an attribute of Car" in logged.pop()

    Person.from_dict({"age": "foo"})
    assert "Can't deserialize Person.age: expecting date, got 'foo'" in logged.pop()

    pp = Person.from_dict({"car": {"make": "Honda", "foo": "bar"}})
    assert pp.car.make == "Honda"
    assert "'foo' is not an attribute of Car" in logged.pop()


def test_string():
    ss = String()
    assert str(ss) == "String"
    assert ss.problem(None) is None
    assert ss.problem("foo") is None
    assert ss.problem(1) == "expecting string, got '1'"

    assert ss.converted(None) is None
    assert ss.converted("foo") == "foo"
    assert ss.converted(1) == "1"
    assert ss.converted([1, 2]) == "[1, 2]"
