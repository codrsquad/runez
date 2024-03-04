import random
import threading

from runez.thread import thread_local_property, ThreadLocalSingleton


class MySingleton(ThreadLocalSingleton):
    def __init__(self):
        self.some_number = random.randint(0, 100000) + random.randint(0, 100000)


def new_singleton():
    return MySingleton()


def test_singleton():
    s1 = MySingleton()
    s2 = MySingleton()
    assert s1 is s2
    assert s1 is new_singleton()

    s3 = run_in_new_thread(MySingleton)
    s4 = run_in_new_thread(new_singleton)
    assert type(s1) is type(s3)
    assert type(s1) is type(s4)
    assert s1 is not s3
    assert s1 is not s4
    assert s3 is not s4


class SomeClass:
    times_called = 0

    @thread_local_property
    def thread_id(self):
        """Testing thread local properties"""
        self.times_called += 1
        return random.randint(0, 100000) + random.randint(0, 100000)

    def get_thread_id(self):
        return self.thread_id


class WrappedRun:
    def __init__(self, target, args, kwargs):
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.result = None

    def run(self):
        self.result = self.target(*self.args, **self.kwargs)


def run_in_new_thread(target, *args, **kwargs):
    wrapper = WrappedRun(target, args, kwargs)
    t = threading.Thread(target=wrapper.run)
    t.start()
    t.join()
    return wrapper.result


def test_thread_local_property():
    prop = SomeClass.thread_id
    assert prop.__name__ == "thread_id"
    assert prop.__doc__ == "Testing thread local properties"

    obj = SomeClass()
    main_tid = obj.get_thread_id()
    assert obj.times_called == 1
    assert main_tid
    assert main_tid == obj.get_thread_id()
    assert obj.times_called == 1

    tid1 = run_in_new_thread(obj.get_thread_id)
    assert tid1 != main_tid
    assert obj.times_called == 2

    tid2 = run_in_new_thread(obj.get_thread_id)
    assert tid2 != main_tid
    assert tid2 != tid1
    assert obj.times_called == 3
