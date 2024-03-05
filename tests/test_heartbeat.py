import time

from runez.heartbeat import DEFAULT_FREQUENCY, Heartbeat, HeartbeatTask


class Counter(HeartbeatTask):
    count = None
    crash = None

    def execute(self):
        if self.count is None:
            self.count = 1

        else:
            self.count += 1

        if self.crash is not None:
            raise self.crash


def do_nothing():
    pass


def test_heartbeat():
    task = Counter()
    crash = Counter(name="crasher")
    crash.crash = ValueError("oops, just crashed")

    # Exercise case with no tasks
    assert len(Heartbeat.tasks) == 0
    Heartbeat.start()
    time.sleep(1.1)
    Heartbeat.stop()
    assert len(Heartbeat.tasks) == 0

    # Exercise case with several tasks
    Heartbeat.add_task(task, frequency=0.7)
    Heartbeat.add_task(crash, frequency=1.5)
    Heartbeat.add_task(do_nothing)
    assert len(Heartbeat.tasks) == 3
    assert Heartbeat.tasks[0].name == "Counter"
    assert Heartbeat.tasks[1].name == "crasher"
    assert Heartbeat.tasks[2].name == "do_nothing"
    Heartbeat.start()
    time.sleep(1.8)
    Heartbeat.remove_task(do_nothing)
    assert len(Heartbeat.tasks) == 2
    Heartbeat.stop()

    assert task.count == 3
    assert crash.count == 2

    Heartbeat.remove_task(crash)
    Heartbeat.remove_task(task)
    assert len(Heartbeat.tasks) == 0


def test_tasks():
    t1 = HeartbeatTask("t1")
    t2 = HeartbeatTask("t2", frequency=10)
    t2.next_execution = 1

    assert str(t1) == "t1 (0)"
    assert t1.frequency == DEFAULT_FREQUENCY
    assert t2.frequency == 10
    assert t1 != t2
    assert t1 <= t2
    assert t1 < t2
