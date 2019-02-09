import time

import runez


def test_tasks():
    t1 = runez.heartbeat.Task("t1")
    t2 = runez.heartbeat.Task("t2", frequency=10)
    t2.next_execution = 1

    assert str(t1) == "t1 (0)"
    assert t1.frequency == runez.heartbeat.DEFAULT_FREQUENCY
    assert t2.frequency == 10
    assert t1 != t2
    assert t1 <= t2
    assert t1 < t2


class Counter(runez.heartbeat.Task):
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

    runez.Heartbeat.add_task(task, frequency=0.1)
    runez.Heartbeat.add_task(crash, frequency=0.2)
    runez.Heartbeat.add_task(do_nothing)

    assert len(runez.Heartbeat.tasks) == 3
    assert len(runez.Heartbeat.upcoming) == 3
    assert runez.Heartbeat.upcoming[0].name == "Counter"
    assert runez.Heartbeat.upcoming[1].name == "crasher"
    assert runez.Heartbeat.upcoming[2].name == "do_nothing"

    runez.Heartbeat.remove_task(do_nothing)
    assert len(runez.Heartbeat.tasks) == 2
    assert len(runez.Heartbeat.upcoming) == 2

    runez.Heartbeat.start()
    time.sleep(0.5)
    runez.Heartbeat.stop()

    assert task.count >= 2
    assert crash.count >= 1

    runez.Heartbeat.remove_task(task)
    runez.Heartbeat.remove_task(crash)
    assert len(runez.Heartbeat.tasks) == 0
    assert len(runez.Heartbeat.upcoming) == 0
