"""
Daemon thread that can be used to run periodical background tasks.

Assumptions:
- Tasks should be reasonably short running (do not use this for long operations)
- Execution frequency should be >= 1 second (this is not designed for very quick frequency)
- Frequency does not dynamically change (stated once at task creation time)
- Tasks should complete within one frequency period (otherwise it'd be continuously called...)

Usage:
    from runez.heartbeat import Heartbeat

    Heartbeat.add_task(report_metrics, frequency=60)
    Heartbeat.add_task(check_something, frequency=30)
    Heartbeat.start()
    ...
    Heartbeat.stop()        # When shutting down
"""

import threading
import time

from runez.system import LOG


DEFAULT_FREQUENCY = 60


class HeartbeatTask(object):
    """Task to be executed periodically"""

    def __init__(self, name=None, frequency=None):
        """
        Args:
            name (str | None): Name of this task (by default: descendant's class name)
            frequency (int | float | None): How often to call 'execute()' on this task, in seconds
        """
        self.name = name or self.__class__.__name__
        self.frequency = frequency or DEFAULT_FREQUENCY
        self.next_execution = 0  # Internal epoch when next execution of this task is due

    def execute(self):
        """Execute this task.

        Either provide a descendant with an implementation for this, or replace this `execute` function with any callable
        """

    def set_next_execution(self):
        """Compute `self.next_execution`"""
        self.next_execution = time.time() + self.frequency

    def __repr__(self):
        return "%s (%s)" % (self.name, self.next_execution)

    def __eq__(self, other):
        return self is other

    def __le__(self, other):
        return (self.next_execution, self.frequency) <= (other.next_execution, other.frequency)

    def __lt__(self, other):
        return (self.next_execution, self.frequency) < (other.next_execution, other.frequency)


class Heartbeat(object):
    """Daemon thread used to run periodical background tasks tasks like:

    - collecting CPU/RAM usage
    - sending metrics
    - refreshing data from a remote server
    """

    tasks = []  # type: list # of task, to be periodically called

    _lock = threading.Lock()
    _thread = None  # Background daemon thread used to periodically execute the tasks
    _last_execution = None  # Epoch when last task execution completed
    _sleep_delay = 1  # How many seconds we're currently sleeping until next task

    @classmethod
    def start(cls):
        """Start background thread if not already started"""
        if cls._thread is None:
            cls._thread = threading.Thread(target=cls._run, name="Heartbeat")
            cls._thread.daemon = True
            cls._thread.start()

    @classmethod
    def stop(cls):
        """Shutdown background thread, stop executing tasks.

        Note that calling this is not usually necessary, we're using a daemon thread, which does not need to be stopped explicitly.
        This can be useful for tests, as they can conveniently start/stop N times
        """
        if cls._thread is not None:
            cls._thread = None

    @classmethod
    def add_task(cls, task, frequency=None):
        """
        Args:
            task (HeartbeatTask | callable): Add 'task' to the list of tasks to run periodically
            frequency (int | float | None): How often to execute this task, in seconds
        """
        with cls._lock:
            if not isinstance(task, HeartbeatTask):
                t = HeartbeatTask(name=task.__name__, frequency=frequency)
                t.execute, task = task, t

            if frequency:
                task.frequency = frequency

            cls.tasks.append(task)
            cls.tasks.sort()

    @classmethod
    def resolved_task(cls, task):
        """
        Args:
            task (HeartbeatTask | callable): Task reference to find

        Returns:
            (HeartbeatTask | None): Task instance representing 'task', if any
        """
        for t in cls.tasks:
            if t is task or t.execute is task:
                return t

    @classmethod
    def remove_task(cls, task):
        """
        Args:
            task (HeartbeatTask | callable): Remove `task` from the list of tasks to run periodically
        """
        with cls._lock:
            if not isinstance(task, HeartbeatTask):
                task = cls.resolved_task(task)

            if task:
                cls.tasks.remove(task)

            cls.tasks.sort()

    @classmethod
    def _execute_task(cls, task):
        try:
            task.execute()

        except Exception as e:
            LOG.warning("HeartbeatTask %s crashed:", task.name, exc_info=e)

        task.set_next_execution()

    @classmethod
    def _run(cls):
        """Background thread's main function, execute registered tasks accordingly to their frequencies"""
        if cls._thread:
            with cls._lock:
                # First run: execute each task once to get it started
                for task in cls.tasks:
                    cls._execute_task(task)

                cls.tasks.sort()
                cls._last_execution = time.time()

        while cls._thread:
            with cls._lock:
                if cls.tasks:
                    for task in cls.tasks:
                        if task.next_execution - cls._last_execution > 0.5:
                            break

                        cls._execute_task(task)

                    cls.tasks.sort()
                    cls._last_execution = time.time()
                    cls._sleep_delay = cls.tasks[0].next_execution - cls._last_execution

                else:
                    cls._sleep_delay = 1

                sleep_delay = max(0.1, cls._sleep_delay)

            # Don't hold cls._lock while sleeping, sleep delay should be 1 second when no tasks are present
            time.sleep(sleep_delay)
