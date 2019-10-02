import threading

_THREAD_LOCAL = threading.local()


class thread_local_property(object):
    """
    A property that is computed once per thread
    Use this in rare cases where you need just a property (or 2) to be thread local in a given object

    If you need an entire object to be thread-local, then use class `ThreadLocalSingleton` instead
    """

    def __init__(self, func):
        self.__doc__ = getattr(func, "__doc__")
        self.name = func.__name__
        self.func = func
        self.thread_local = threading.local()

    def __get__(self, obj, cls):
        if obj is None:
            return self

        if not hasattr(self.thread_local, self.name):
            setattr(self.thread_local, self.name, self.func(obj))

        return getattr(self.thread_local, self.name)


class ThreadLocalSingleton(object):
    """
    Class ancestor intended to easily allow you to get per-thread singletons

    Usage:
        class MyClass(ThreadLocalSingleton):
            def __init__(...):
                # Will be called once per thread, no matter how many times or where it gets invoked from
                ...
    """
    def __new__(cls, *args, **kwargs):
        # We could do singleton by combination of args, but outcome of that could be hard to grok for users
        # Not sure if there's a good use case for this (one where gotcha-factor is much lower than added value)
        assert not args and not kwargs, "Current limitation: only classes that can be created without args are supported for now"

        key = "singleton %s.%s" % (cls.__module__, cls.__name__)
        existing = getattr(_THREAD_LOCAL, key, None)
        if existing is None:
            existing = super(ThreadLocalSingleton, cls).__new__(cls, *args, **kwargs)
            setattr(_THREAD_LOCAL, key, existing)

        return existing
