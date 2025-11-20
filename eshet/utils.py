import asyncio
import functools
import traceback
from dataclasses import dataclass
import typing


def create_task_in_set(s: set, coro):
    """helper to call create_task(coro), save the result in s, and remove it
    when it's done; returns the task
    """
    task = asyncio.create_task(coro)
    s.add(task)
    task.add_done_callback(s.remove)
    return task


def in_task(f):
    """decorator: return a function which calls f in a task"""
    tasks = set()

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return create_task_in_set(tasks, f(*args, **kwargs))

    return wrapper


Task = typing.Callable[[], typing.Awaitable[None]]


class TaskStrategy:
    """a strategy for running tasks in the background

    call build to get an implementation object, which can be called with tasks
    (no-argument async functions), and will run them in the background
    according to some defined strategy
    """

    def build(self) -> typing.Callable[[Task], None]:
        """instantiate this strategy

        The return value can be called with a task to run it in the specified way.
        """
        raise NotImplementedError()  # pragma: no cover

    def wrap_fn(self, f):
        """the returned function calls the wrapped function in an instance of
        this strategy"""
        instance = self.build()

        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            return instance(lambda: f(*args, **kwargs))

        return wrapper


@dataclass(frozen=True)
class RunInTask(TaskStrategy):
    """strategy for running tasks in separate asyncio tasks"""

    def build(self):
        return _RunInTaskImpl()


class _RunInTaskImpl:
    def __init__(self):
        self.tasks = set()

    def __call__(self, task):
        return create_task_in_set(self.tasks, task())

    async def close(self):
        pass


@dataclass(frozen=True)
class RunSerially(TaskStrategy):
    """strategy for running tasks serially, which allows retries and queue
    jumping

    tasks are pushed to a queue, and are ran in a background task
    """

    only_latest: bool = False
    """skip tasks is there is more than one in the queue

    this is useful for idempotent tasks
    """

    retry: bool = False
    """retry failed tasks

    the delay between runs starts at retry_start and is multiplied by
    retry_multiplier each time, up to a maximum of retry_end
    """

    assume_failed: bool = False
    """assume that the task has failed, even if it succeeds

    this is useful for tasks which do something inherently unreliable (e.g.
    sending a message on an unreliable medium); retry and only_latest must be
    set if this is
    """

    retry_start: float = 2.0
    retry_end: float = 30.0
    retry_multiplier: float = 2.0

    def build(self):
        # combinations of only_latest, retry and assume_failed
        #
        # OK:
        # FFF: just serial
        # TFF: serial, long running
        # TTF: retry with reliable status, setting state
        # FTF: retry with reliable status, adds to state
        # TTT: retry with unreliable status
        #
        # not OK:
        # FxT: if we always retry, we need to move on to the next at some point
        # xFT: no point in assuming failed if not retrying

        if self.assume_failed:
            assert self.only_latest, "only_latest must be set if assume_failed is"
            assert self.retry, "retry must be set if assume_failed is"

        return _RunSeriallyImpl(self)


class _RunSeriallyImpl:
    def __init__(self, options):
        self.options = options

        self.queue = asyncio.Queue()

        self.run_loop = asyncio.create_task(self._run_loop())

    def __call__(self, task):
        self.queue.put_nowait(task)

    async def close(self):
        self.run_loop.cancel()
        try:
            await self.run_loop
        except asyncio.CancelledError:
            pass

    async def _run_loop(self):
        failed = False  # did the last task fail?
        timeout = self.options.retry_start  # time to wait between retries

        while True:
            first_try = False  # is this the first time we've ran this task

            # get a task to run and/or wait for timeout
            if failed and self.options.retry:
                # potentially use last task
                if self.options.only_latest:
                    # wait, but switch to new task if one appears
                    try:
                        task = await asyncio.wait_for(self.queue.get(), timeout)
                        first_try = True
                    except asyncio.TimeoutError:
                        pass
                else:
                    # just wait and use last task
                    await asyncio.sleep(timeout)
            else:
                task = await self.queue.get()
                first_try = True

            # skip to the last task
            if self.options.only_latest:
                while not self.queue.empty():
                    task = self.queue.get_nowait()

            # run it
            try:
                await task()
                failed = self.options.assume_failed
            except Exception:
                traceback.print_exc()
                failed = True

            # figure out the timeout for the next round
            if failed:
                if first_try:
                    timeout = self.options.retry_start
                else:
                    timeout = min(
                        timeout * self.options.retry_multiplier, self.options.retry_end
                    )
