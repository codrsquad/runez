import pytest

import runez
from runez.schema import Any, Date, Dict, Integer, List, Serializable, String


def test_any():
    any = Any()
    assert any.problem(None, None) is None
    assert any.problem("a", None) is None
    assert any.problem(4, None) is None
    assert any.problem([1, 2], None) is None
    assert any.problem(object(), None) is None


def test_dict():
    dd = Dict()
    assert str(dd) == "dict[*, *]"
    assert dd.problem({}, None) is None
    assert dd.problem({1: "a"}, None) is None
    assert dd.problem({"a": 1}, None) is None

    dd = Dict(String)
    assert str(dd) == "dict[string, *]"
    assert dd.problem({}, None) is None
    assert dd.problem({1: "a"}, None) == "key: expecting string, got '1'"
    assert dd.problem({"a": 1}, None) is None

    dd = Dict(String, Integer)
    assert str(dd) == "dict[string, integer]"
    assert dd.problem(5, None) == "expecting dict, got '5'"
    assert dd.problem({}, None) is None
    assert dd.problem({1: "a"}, None) == "key: expecting string, got '1'"
    assert dd.problem({"a": "b"}, None) == "value: 'b' is not an integer"
    assert dd.problem({"a": 1}, None) is None

    assert dd.converted({"a": 1}, None) == {"a": 1}
    assert dd.converted({"a": "1"}, None) == {"a": 1}

    dd = Dict(String, List(Integer))
    assert str(dd) == "dict[string, list[integer]]"
    assert dd.problem({}, None) is None
    assert dd.problem({"a": "b"}, None) == "value: expecting list, got 'b'"
    assert dd.problem({"a": ["1"]}, None) is None
    assert dd.problem({"a": ["b"]}, None) == "value: 'b' is not an integer"


def test_list():
    ll = List()
    assert str(ll) == "list[*]"
    assert ll.problem([], None) is None
    assert ll.problem(["a"], None) is None
    assert ll.problem([1, 2], None) is None
    assert ll.problem({1, "2"}, None) is None

    assert ll.converted([1, "2"], None) == [1, "2"]

    ll = List(Integer)
    assert str(ll) == "list[integer]"
    assert ll.problem([], None) is None
    assert ll.problem(["a"], None) == "'a' is not an integer"
    assert ll.problem([1, 2], None) is None
    assert ll.problem((1, 2), None) is None
    assert ll.problem({1, "2"}, None) is None

    assert ll.converted([1, "2"], None) == [1, 2]
    assert ll.converted((1, 2), None) == [1, 2]
    assert sorted(ll.converted({1, "2"}, None)) == [1, 2]


class Car(runez.Serializable):
    make = String
    year = Integer


class Hat(runez.Serializable):
    size = Integer(default=1)


class Person(runez.Serializable):
    age = Date
    first_name = String(default="joe")
    last_name = String(default="smith")

    car = Car
    hat = Serializable(Hat)


def test_serializable(logged):
    assert str(Person._meta) == "Person (5 attributes, 0 properties)"

    pp = Person()
    assert pp.age is None
    assert pp.first_name == "joe"
    assert pp.last_name == "smith"
    assert pp.car is None

    with pytest.raises(runez.system.AbortException):
        Person.from_dict({"car": "foo"})
    assert "Can't deserialize Person.car: expecting compliant dict, got 'foo'" in logged.pop()

    with pytest.raises(runez.system.AbortException):
        Person.from_dict({"hat": {"size": "foo"}})
    assert "Can't deserialize Person.hat: 'foo' is not an integer" in logged.pop()

    pp = Person.from_dict({"age": "2019-01-01", "car": {"make": "Honda", "year": 2010}})
    assert pp.age.year == 2019
    assert pp.car.make == "Honda"
    assert pp.car.year == 2010
    assert pp.to_dict() == {"age": "2019-01-01", "car": {"make": "Honda", "year": 2010}, "first_name": "joe", "last_name": "smith"}

    pp = Person.from_dict({"age": 1567296012})
    assert pp.age.year == 2019
    assert pp.to_dict() == {"age": "2019-09-01 00:00:12+00:00", "first_name": "joe", "last_name": "smith"}

    pp = Person.from_dict({"car": {"make": "Honda", "foo": "bar"}}, ignore=False)
    assert pp.car.make == "Honda"
    assert "Extra content given for Car: foo" in logged.pop()

    with pytest.raises(runez.system.AbortException):
        Person.from_dict({"car": {"make": "Honda", "foo": "bar"}}, ignore=None)
    assert "Can't deserialize Person.car: foo is not an attribute" in logged.pop()

    with pytest.raises(runez.system.AbortException):
        Person.from_dict({"age": "foo"})
    assert "Can't deserialize Person.age: expecting date, got 'foo'" in logged.pop()
