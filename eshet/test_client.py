from .client import Client
import pytest
import asyncio


@pytest.fixture
async def client():
    c = Client(base="/test_client")
    await c.wait_for_connection()

    yield c

    await c.close()


async def test_action(client):
    await client.action_register("test_action", lambda x: x + 1)

    res = await client.action_call("test_action", 5)
    assert res == 6


async def test_action_absolute_call(client):
    await client.action_register("test_action", lambda x: x + 1)

    res = await client.action_call("/test_client/test_action", 5)
    assert res == 6


async def test_async_action(client):
    async def async_action(x):
        await asyncio.sleep(0)
        return x + 1

    await client.action_register("test_async_action", async_action)
    res = await client.action_call("test_async_action", 5)
    assert res == 6


async def test_event(client):
    event = await client.event_register("test_event")

    # check callbacks, async callbacks, and multiple registrations
    calls = asyncio.Queue()
    await client.event_listen_cb("test_event", calls.put_nowait)

    async_calls = asyncio.Queue()
    await client.event_listen_cb("test_event", async_calls.put)

    await event(5)
    assert await calls.get() == 5
    assert await async_calls.get() == 5

    # check they were only called once
    await asyncio.sleep(0.3)
    assert calls.empty() and async_calls.empty()


async def test_event_iter(client):
    event = await client.event_register("test_event_iter")

    payloads = asyncio.Queue()

    async def task_fn():
        async for payload in client.event_listen("test_event_iter"):
            payloads.put_nowait(payload)
            if payload == "bar":
                break

    task = asyncio.create_task(task_fn())

    # need to wait for listen to actually happen
    await asyncio.sleep(0.3)

    for payload in "foo", "bar":
        await event(payload)
        assert await payloads.get() == payload

    await task
