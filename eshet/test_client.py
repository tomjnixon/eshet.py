from .client import Client, Unknown
import pytest
import asyncio
import logging


@pytest.fixture
async def client():
    c = Client(
        base="/test_client",
        logger=logging.getLogger("client"),
    )
    await c.wait_for_connection()

    yield c

    await c.close()


@pytest.fixture
async def client2():
    c = Client(
        base="/test_client",
        logger=logging.getLogger("client2"),
    )
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


async def test_state(client):
    state = await client.state_register("test_state")

    calls = asyncio.Queue()
    value = await client.state_observe("test_state", calls.put_nowait)
    assert value is Unknown

    # no initial calls
    await asyncio.sleep(0.3)
    assert calls.empty()

    # changes get through
    await state.changed(5)

    assert (await calls.get()) == 5
    await asyncio.sleep(0.3)
    assert calls.empty()

    # another observer
    calls2 = asyncio.Queue()
    value = await client.state_observe("test_state", calls2.put_nowait)
    assert value == 5

    # no initial calls
    await asyncio.sleep(0.3)
    assert calls2.empty()

    # set unknown
    await state.unknown()

    assert (await calls.get()) is Unknown
    assert (await calls2.get()) is Unknown

    await asyncio.sleep(0.3)
    assert calls.empty()
    assert calls2.empty()


async def test_state_observe_twice(client):
    state = await client.state_register("test_state")
    await state.changed(5)

    async def observe():
        calls = asyncio.Queue()
        value = await client.state_observe("test_state", calls.put_nowait)
        assert value == 5

        await asyncio.sleep(0.3)
        assert calls.empty()

    t1 = asyncio.create_task(observe())
    t2 = asyncio.create_task(observe())
    await t1
    await t2


async def test_state_observe_reconnect(client, client2):
    state = await client.state_register("test_state")
    await state.changed(5)

    calls = asyncio.Queue()
    value = await client2.state_observe("test_state", calls.put_nowait)
    assert value == 5

    client2.protocol.transport.close()

    assert (await calls.get()) is Unknown
    assert (await calls.get()) == 5

    await asyncio.sleep(0.3)
    assert calls.empty()


async def test_state_observe_during_reconnect(client, client2):
    state = await client.state_register("test_state")
    await state.changed(5)

    client2.protocol.transport.close()
    await asyncio.sleep(0.5)

    calls = asyncio.Queue()
    value = await client2.state_observe("test_state", calls.put_nowait)
    assert value == 5

    client2.protocol.transport.close()

    assert (await calls.get()) is Unknown
    assert (await calls.get()) == 5

    await asyncio.sleep(0.3)
    assert calls.empty()


async def test_state_get(client):
    state = await client.state_register("test_state")
    await state.changed(5)

    assert (await client.get("test_state")) == 5


async def test_state_set(client, client2):
    calls = asyncio.Queue()
    state = await client.state_register("test_state", calls.put_nowait)

    await client2.set("test_state", 7)

    assert (await calls.get()) == 7
    await asyncio.sleep(0.3)
    assert calls.empty()
