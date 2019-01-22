import time

from runez.heartbeat import DEFAULT_FREQUENCY, Heartbeat, Task


def test_tasks():
    t1 = Task("t1")
    t2 = Task("t2", frequency=10)
    t2.next_execution = 1

    assert str(t1) == "t1 (0)"
    assert t1.frequency == DEFAULT_FREQUENCY
    assert t2.frequency == 10
    assert t1 != t2
    assert t1 <= t2
    assert t1 < t2


class Counter(Task):
    count = None
    crash = False

    def execute(self):
        if self.count is None:
            self.count = 1
        else:
            self.count += 1
        if self.crash:
            raise Exception("oops, just crashed")


def do_nothing():
    pass


def test_heartbeat():
    task = Counter()
    crash = Counter(name="crasher")
    crash.crash = True

    Heartbeat.add_task(task, frequency=0.1)
    Heartbeat.add_task(crash, frequency=0.2)
    Heartbeat.add_task(do_nothing)

    assert len(Heartbeat.tasks) == 3
    assert len(Heartbeat.upcoming) == 3
    assert Heartbeat.upcoming[0].name == "Counter"
    assert Heartbeat.upcoming[1].name == "crasher"
    assert Heartbeat.upcoming[2].name == "do_nothing"

    Heartbeat.remove_task(do_nothing)
    assert len(Heartbeat.tasks) == 2
    assert len(Heartbeat.upcoming) == 2

    Heartbeat.start()
    time.sleep(0.5)
    Heartbeat.stop()

    assert task.count >= 2
    assert crash.count >= 1

    Heartbeat.remove_task(task)
    Heartbeat.remove_task(crash)
    assert len(Heartbeat.tasks) == 0
    assert len(Heartbeat.upcoming) == 0
