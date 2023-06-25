import asyncio
import pytest
from .utils import RunInTask, RunSerially
from dataclasses import dataclass


@pytest.fixture(scope="function")
def event_loop():
    from asyncio_time_travel import TimeTravelLoop

    loop = TimeTravelLoop()
    yield loop
    loop.close()


retry_opts = dict(
    retry_start=1.0,
    retry_end=3.0,
    retry_multiplier=2.0,
)


@dataclass
class Task:
    time: float = 1.0
    count: int = 0
    raises: int = 0

    async def __call__(self):
        if self.raises > 0:
            self.raises -= 1
            self.count += 1
            raise RuntimeError("oops")
        await asyncio.sleep(self.time)
        self.count += 1


async def test_RunInTask():
    runner = RunInTask().build()

    t1 = Task()
    runner(t1)
    t2 = Task()
    runner(t2)

    await asyncio.sleep(1.5)

    assert t1.count == 1
    assert t2.count == 1

    await runner.close()


async def test_RunSerially_no_retry():
    runner = RunSerially().build()

    t1 = Task()
    runner(t1)
    t2 = Task()
    runner(t2)

    await asyncio.sleep(1.5)

    assert t1.count == 1
    assert t2.count == 0

    await asyncio.sleep(1.5)

    assert t1.count == 1
    assert t2.count == 1

    await runner.close()


async def test_RunSerially_no_retry_exc():
    runner = RunSerially().build()

    t1 = Task(raises=1)
    runner(t1)
    t2 = Task()
    runner(t2)

    await asyncio.sleep(1.5)

    assert t1.count == 1
    assert t2.count == 1

    await runner.close()


async def test_RunSerially_retry_exc():
    runner = RunSerially(retry=True, **retry_opts).build()

    t1 = Task(raises=4)
    runner(t1)
    t2 = Task()
    runner(t2)

    await asyncio.sleep(0.5)

    assert t1.count == 1
    assert t2.count == 0

    await asyncio.sleep(1.0)

    assert t1.count == 2
    assert t2.count == 0

    await asyncio.sleep(2.0)

    assert t1.count == 3
    assert t2.count == 0

    await asyncio.sleep(3.0)  # limited timeout

    assert t1.count == 4
    assert t2.count == 0

    await asyncio.sleep(4.0)  # timeout plus 1s for task to run

    assert t1.count == 5
    assert t2.count == 0

    await asyncio.sleep(1.0)

    assert t1.count == 5
    assert t2.count == 1

    await runner.close()


async def test_RunSerially_only_latest():
    runner = RunSerially(only_latest=True, **retry_opts).build()

    t1 = Task()
    runner(t1)

    await asyncio.sleep(0.5)

    t2 = Task()
    runner(t2)
    t3 = Task()
    runner(t3)

    await asyncio.sleep(1.0)

    assert t1.count == 1
    assert t2.count == 0
    assert t3.count == 0

    await asyncio.sleep(1.0)

    assert t1.count == 1
    assert t2.count == 0
    assert t3.count == 1

    await runner.close()


async def test_RunSerially_only_latest_retry():
    runner = RunSerially(retry=True, only_latest=True, **retry_opts).build()

    t1 = Task(raises=1)
    runner(t1)

    await asyncio.sleep(0.5)

    assert t1.count == 1

    t2 = Task()
    runner(t2)

    await asyncio.sleep(1.5)

    assert t1.count == 1
    assert t2.count == 1

    await runner.close()


async def test_RunSerially_assume_failed():
    runner = RunSerially(
        only_latest=True, retry=True, assume_failed=True, **retry_opts
    ).build()

    t1 = Task()
    runner(t1)

    await asyncio.sleep(1.5)

    assert t1.count == 1

    await asyncio.sleep(2.0)  # 1 for timeout, 1 for task

    assert t1.count == 2

    await runner.close()
