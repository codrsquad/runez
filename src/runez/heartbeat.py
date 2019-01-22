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

import logging
import threading
import time


DEFAULT_FREQUENCY = 60


class Task:
    """Task to be executed periodically"""

    def __init__(self, name=None, frequency=None):
        """
        :param str|None name: Name of this task (by default: descendant's class name)
        :param int|float|None frequency: How often to call 'execute()' on this task, in seconds
        """
        self.name = name or self.__class__.__name__
        self.frequency = frequency or DEFAULT_FREQUENCY
        # Internal epoch when next execution of this task is due
        self.next_execution = 0

    def execute(self):
        """
        Execute this task
        Either provide a descendant with an implementation for this, or replace this 'execute' function with any callable
        """

    def __repr__(self):
        return "%s (%s)" % (self.name, self.next_execution)

    def __eq__(self, other):
        return self is other

    def __le__(self, other):
        return self.next_execution <= other.next_execution

    def __lt__(self, other):
        return self.next_execution < other.next_execution


class Heartbeat:
    """
    Daemon thread used to run periodical background tasks tasks like:

    - collecting CPU/RAM usage
    - sending metrics
    - refreshing data from a remote server
    """

    tasks = []  # list(Task) # List of functions to be periodically called
    upcoming = []  # list(Task) # Ordered list of next tasks to run

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
        """
        Shutdown background thread, stop executing tasks

        Note that calling this is not usually necessary, we're using a daemon thread, which does not need to be stopped explicitly.
        This can be useful for tests, as they can conveniently start/stop N times
        """
        if cls._thread is not None:
            cls._thread = None

    @classmethod
    def add_task(cls, task, frequency=None):
        """
        :param Task|callable task: Add 'task' to the list of tasks to run periodically
        :param int|float|None frequency: Frequency at which to execute the task
        """
        with cls._lock:
            if isinstance(task, Task):
                cls.tasks.append(task)
                if frequency:
                    task.frequency = frequency

            else:
                new_task = Task(name=task.__name__, frequency=frequency)
                new_task.execute = task
                cls.tasks.append(new_task)
                task = new_task

            task.next_execution = time.time() + task.frequency
            cls.upcoming.append(task)
            cls.upcoming.sort()

    @classmethod
    def resolved_task(cls, task):
        """Task instance representing 'task', if any"""
        for t in cls.tasks:
            if t == task or t.execute == task:
                return t

    @classmethod
    def remove_task(cls, task):
        """
        :param Task|callable task: Remove 'task' from the list of tasks to run periodically
        """
        with cls._lock:
            if not isinstance(task, Task):
                task = cls.resolved_task(task)

            if task:
                cls.tasks.remove(task)
                cls.upcoming.remove(task)

            if not cls.upcoming:
                # Edge case: when no tasks are to be executed, check for task additions every second
                cls._sleep_delay = 1

    @classmethod
    def _run(cls):
        """Background thread's main function, execute registered tasks accordingly to their frequencies"""
        while cls._thread:
            with cls._lock:
                if cls.upcoming:
                    # Execute next upcoming task
                    task = cls.upcoming[0]
                    # Bump before execution so task run time does not influence its frequency
                    task.next_execution = time.time() + task.frequency
                    # This will sort by next_execution time
                    cls.upcoming.sort()

                    try:
                        task.execute()

                    except Exception as e:
                        # Log only if user set up logging
                        if logging.root:
                            logging.root.warning("Task %s crashed:", task.name, exc_info=e)

                    cls._last_execution = time.time()
                    cls._sleep_delay = cls.upcoming[0].next_execution - cls._last_execution

            # Don't hold cls._lock while sleeping, sleep delay should be 1 second when no tasks are present
            time.sleep(max(0.1, cls._sleep_delay))
