# Async @runez.cached_property

`@runez.cached_property` can be made to support async properties, but I think it's not worth the trouble.
Keeping code here until someone asks for the feature.

Current version in runez does not try and support threads nor async calls.

The version below was tested with both thread locks and asyncio, if supporting that becomes useful one day.

- In `system.py`:

```python
import threading
from functools import wraps

try:
    import asyncio

except (ImportError, SyntaxError):
    asyncio = None


class cached_property(object):
    """
    A property that is only computed once per instance and then replaces itself with an ordinary attribute.
    Same as https://pypi.org/project/cached-property/ (without having to add another dependency).

    This version is always thread safe, and usable with asyncio.
    Deleting the attribute resets the property.
    """

    def __init__(self, func):
        self.func = func
        self.__annotations__ = getattr(func, "__annotations__", None)
        self.__doc__ = func.__doc__
        self.__module__ = func.__module__
        self.__name__ = func.__name__
        self.is_async = asyncio and asyncio.iscoroutinefunction(self.func)
        if self.is_async:
            self._compute_value = self._future_value

        self.lock = threading.RLock()

    def __delete__(self, instance):
        with self.lock:
            try:
                del instance.__dict__[self.__name__]

            except (AttributeError, KeyError):
                pass

    def __set__(self, instance, value):
        with self.lock:
            instance.__dict__[self.__name__] = value

    def __get__(self, instance, owner):
        if instance is None:
            return self

        if self.is_async:
            @wraps(instance)
            @asyncio.coroutine
            def wrapper():
                return self._atomic_get(instance)

            return wrapper()

        return self._atomic_get(instance)

    def _atomic_get(self, instance):
        # Atomically replace this property with computed value on first call
        with self.lock:
            instance_dict = instance.__dict__
            name = self.__name__
            try:
                return instance_dict[name]  # Another thread already computed the value

            except KeyError:
                value = self._compute_value(instance)  # We're the first thread to compute the value
                instance_dict[name] = value
                return value

    def _compute_value(self, instance):
        # Default case: no asyncio is involved
        return self.func(instance)

    def _future_value(self, instance):
        # Replacement for _compute_value() in asyncio case
        return asyncio.ensure_future(self.func(instance))

```

- add this to `tests/requirements.txt`:

```
pytest-asyncio; python_version >= '3'
```

- `tests/test_cached_property.py`:

```python
import random
import threading
import time

from runez.system import cached_property


class MyObject:

    _global_counter = 1  # Used as a global counter

    @cached_property
    def foo(self):
        MyObject._global_counter += 1
        return MyObject._global_counter


def simple_check(obj1, obj2):
    assert obj1.foo == 2
    assert obj2.foo == 3


def complex_check(obj1, obj2):
    del obj1.foo
    assert obj1.foo
    time.sleep(random.random() / 100)
    del obj2.foo
    assert obj2.foo


def run_threads(thread_count, func, *args):
    threads = []
    for _ in range(thread_count):
        thread = threading.Thread(target=func, args=args)
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()


def test_multithreaded():
    MyObject._global_counter = 1
    obj1 = MyObject()
    obj2 = MyObject()
    assert obj1.foo == 2
    assert obj2.foo == 3

    # Simple check doesn't delete any property (thus, they don't change)
    run_threads(10, simple_check, obj1, obj2)
    assert obj1.foo == 2
    assert obj2.foo == 3

    # Complex check deletes property every time, triggering a new value each time
    run_threads(10, complex_check, obj1, obj2)
    assert obj1.foo >= 10
    assert obj2.foo >= 10
```


- `tests/test_async.py`:

```python
import pytest

from runez.system import cached_property


class MyObject:

    _foo = 1  # Used as a global counter

    @cached_property
    async def foo(self):
        MyObject._foo += 1
        return MyObject._foo


@pytest.mark.asyncio
async def test_async():
    assert True
    obj1 = MyObject()
    del obj1.foo
    assert await obj1.foo == 2

    obj2 = MyObject()
    assert await obj1.foo == 2  # Check that it didn't change
    assert await obj2.foo == 3  # Freshly computed in new object

    del obj1.foo
    assert await obj1.foo == 4  # Recomputed after delete
    assert await obj2.foo == 3  # Other object was unaffected

    obj1.foo = 42
    assert await obj1.foo == 42  # Setting value works
    assert await obj2.foo == 3  # And does not affect other object
```
