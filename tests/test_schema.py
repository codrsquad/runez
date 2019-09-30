import logging

from runez.schema import Any, Date, Dict, Float, Integer, List, MetaSerializable, String
from runez.serialize import Serializable, with_behavior


def test_any():
    any = Any()
    assert any.problem(None) is None
    assert any.problem("a") is None
    assert any.problem(4) is None
    assert any.problem([1, 2]) is None
    assert any.problem(object()) is None


def test_dict():
    dd = Dict()
    assert str(dd) == "dict[*, *]"
    assert dd.problem({}) is None
    assert dd.problem({1: "a"}) is None
    assert dd.problem({"a": 1}) is None

    dd = Dict(String)
    assert str(dd) == "dict[string, *]"
    assert dd.problem({}) is None
    assert dd.problem({1: "a"}) == "key: expecting string, got '1'"
    assert dd.problem({"a": 1}) is None

    dd = Dict(String, Integer)
    assert str(dd) == "dict[string, integer]"
    assert dd.problem(5) == "expecting dict, got '5'"
    assert dd.problem({}) is None
    assert dd.problem({1: "a"}) == "key: expecting string, got '1'"
    assert dd.problem({"a": "b"}) == "value: expecting int, got 'b'"
    assert dd.problem({"a": 1}) is None

    assert dd.converted({"a": 1}) == {"a": 1}
    assert dd.converted({"a": "1"}) == {"a": 1}

    dd = Dict(String, List(Integer))
    assert str(dd) == "dict[string, list[integer]]"
    assert dd.problem({}) is None
    assert dd.problem({"a": "b"}) == "value: expecting list, got 'b'"
    assert dd.problem({"a": ["1"]}) is None
    assert dd.problem({"a": ["b"]}) == "value: expecting int, got 'b'"


def test_list():
    ll = List()
    assert str(ll) == "list[*]"
    assert ll.problem([]) is None
    assert ll.problem(["a"]) is None
    assert ll.problem([1, 2]) is None
    assert ll.problem({1, "2"}) is None

    assert ll.converted([1, "2"]) == [1, "2"]

    ll = List(Integer)
    assert str(ll) == "list[integer]"
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
    assert str(ff) == "float"
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
    year = Integer


class Hat(Serializable, with_behavior(extras=False)):
    size = Integer(default=1)


class Person(Serializable, with_behavior(strict=logging.error, hook=logging.info)):
    age = Date
    first_name = String(default="joe")
    last_name = String(default="smith")

    car = Car
    hat = MetaSerializable(Hat)


class SpecializedPerson(Person):
    """Used to test that ._meta.behavior is passed on to descendants as well"""


def test_serializable(logged):
    assert str(Person._meta) == "Person (5 attributes, 0 properties)"
    assert str(Car._meta.behavior) == "extras: function 'info', ignored extras: [foo, bar]"
    assert str(Hat._meta.behavior) == "lenient"
    assert str(Person._meta.behavior) == "strict: function 'error', extras: function 'debug', hook: function 'info'"
    assert str(SpecializedPerson._meta.behavior) == "strict: function 'error', extras: function 'debug', hook: function 'info'"

    Car.from_dict({"foo": 1, "baz": 2})
    assert "foo" not in logged
    assert "Extra content given for Car: baz" in logged.pop()

    pp = Person()
    assert pp.age is None
    assert pp.first_name == "joe"
    assert pp.last_name == "smith"
    assert pp.car is None

    Person.from_dict({"car": "foo"})
    assert "Can't deserialize Person.car: expecting compliant dict, got 'foo'" in logged.pop()

    Person.from_dict({"hat": {"size": "foo"}})
    assert "Can't deserialize Person.hat: expecting int, got 'foo'" in logged.pop()

    pp = Person.from_dict({"age": "2019-01-01", "car": {"make": "Honda", "year": 2010}})
    assert pp.age.year == 2019
    assert pp.car.make == "Honda"
    assert pp.car.year == 2010
    assert pp.to_dict() == {"age": "2019-01-01", "car": {"make": "Honda", "year": 2010}, "first_name": "joe", "last_name": "smith"}

    pp = Person.from_dict({"age": 1567296012})
    assert pp.age.year == 2019
    assert pp.to_dict() == {"age": "2019-09-01 00:00:12+00:00", "first_name": "joe", "last_name": "smith"}

    Person.from_dict({"car": {"make": "Honda", "foo": "bar"}})
    assert "'foo' is not an attribute of Car" in logged.pop()

    Person.from_dict({"age": "foo"})
    assert "Can't deserialize Person.age: expecting date, got 'foo'" in logged.pop()

    pp = Person.from_dict({"car": {"make": "Honda", "foo": "bar"}})
    assert pp.car.make == "Honda"
    assert "'foo' is not an attribute of Car" in logged.pop()
