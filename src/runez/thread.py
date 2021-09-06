from runez.system import py_mimic, THREAD_LOCAL


class thread_local_property:
    """
    A property that is computed once per thread
    Use this in rare cases where you need just a property (or 2) to be thread local in a given object

    If you need an entire object to be thread-local, then use class `ThreadLocalSingleton` instead
    """

    def __init__(self, func):
        self.__func__ = func
        self.key = "_tp%s" % func.__qualname__
        py_mimic(self, func)

    def __get__(self, instance, owner):
        if instance is None:
            return self

        if not hasattr(THREAD_LOCAL, self.key):
            setattr(THREAD_LOCAL, self.key, self.__func__(instance))

        return getattr(THREAD_LOCAL, self.key)


class ThreadLocalSingleton:
    """
    Class ancestor intended to easily allow you to get per-thread singletons

    Usage:
        class MyClass(ThreadLocalSingleton):
            def __init__(...):
                # Will be called once per thread, no matter how many times or where it gets invoked from
                ...
    """

    def __new__(cls, *positional, **named):
        # We could do singleton by combination of args, but outcome of that could be hard to grok for users
        # Not sure if there's a good use case for this (one where gotcha-factor is much lower than added value)
        assert not positional and not named, "Current limitation: only classes that can be created without args are supported for now"

        key = "_ts%s.%s" % (cls.__module__, cls.__name__)
        existing = getattr(THREAD_LOCAL, key, None)
        if existing is None:
            existing = super().__new__(cls)
            setattr(THREAD_LOCAL, key, existing)

        return existing
