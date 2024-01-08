from unittest.mock import Mock, call
from .yarp import (
    action_call,
    event_listen,
    replace_unknown,
    state_observe,
    state_register,
    state_register_set_event,
    set_value,
)
from yarp import Event, Value, NoValue
import asyncio
import gc
import pytest
from .client import Client, Unknown
import logging


@pytest.fixture
async def client():
    c = Client(
        base="/test_client_yarp",
        logger=logging.getLogger("client"),
    )
    await c.wait_for_connection()

    yield c

    await c.close()


@pytest.fixture
async def client2():
    c = Client(
        base="/test_client_yarp",
        logger=logging.getLogger("client2"),
    )
    await c.wait_for_connection()

    yield c

    await c.close()


@pytest.mark.needs_server
async def test_event_listen(client, client2):
    event = await client.event_register("test_event")

    e = await event_listen("test_event", client=client2)
    gc.collect()
    events = []
    e.on_event(events.append)

    await event(5)
    await asyncio.sleep(0.5)
    assert events == [5]

    await event(6)
    await asyncio.sleep(0.5)
    assert events == [5, 6]


@pytest.mark.needs_server
async def test_state_observe(client, client2):
    state = await client.state_register("test_state")

    v = await state_observe("test_state", client=client2)
    gc.collect()
    values = []
    v.on_value_changed(values.append)

    assert v.value is Unknown

    await state.changed(5)
    await asyncio.sleep(0.5)
    assert values == [5]

    await state.changed(6)
    await asyncio.sleep(0.5)
    assert values == [5, 6]

    await state.unknown()
    await asyncio.sleep(0.5)
    assert values == [5, 6, Unknown]


@pytest.mark.needs_server
@pytest.mark.parametrize("initial_value", [NoValue, 5])
async def test_state_register(client, client2, initial_value):
    v = Value(initial_value)

    await state_register(f"test_state2_{initial_value}", v, client=client2)
    gc.collect()

    values = []
    value = await client.state_observe(f"test_state2_{initial_value}", values.append)
    assert value == Unknown if initial_value is NoValue else initial_value

    v.value = 6
    await asyncio.sleep(0.5)
    assert values == [6]


@pytest.mark.needs_server
@pytest.mark.parametrize("initial_value", [NoValue, 5])
async def test_state_register_settable(client, client2, initial_value):
    v = Value(initial_value)

    await state_register("test_state3", v, client=client2, settable=True)
    gc.collect()

    values = []
    value = await client.state_observe("test_state3", values.append)
    assert value == Unknown if initial_value is NoValue else initial_value

    # can set state from Value
    v.value = 6
    await asyncio.sleep(0.5)
    assert values == [6]

    # can set Value from state
    await client.set("test_state3", 7)
    await asyncio.sleep(0.5)
    assert v.value == 7
    assert values == [6, 7]


@pytest.mark.needs_server
@pytest.mark.parametrize("initial_value", [NoValue, 5])
async def test_state_register_set_callback(client, client2, initial_value):
    v = Value(initial_value)

    set_values = []
    await state_register(
        "test_state4", v, set_callback=set_values.append, client=client2
    )
    gc.collect()

    values = []
    value = await client.state_observe("test_state4", values.append)
    assert value == Unknown if initial_value is NoValue else initial_value

    # can set state from Value
    v.value = 6
    await asyncio.sleep(0.5)
    assert values == [6]

    # can set Value from state, causing a callback
    await client.set("test_state4", 7)
    await asyncio.sleep(0.5)
    # no change
    assert v.value == 6
    assert values == [6]
    # event
    assert set_values == [7]


@pytest.mark.needs_server
@pytest.mark.parametrize("initial_value", [NoValue, 5])
async def test_state_register_set_event(client, client2, initial_value):
    v = Value(initial_value)

    on_set = await state_register_set_event("test_state4", v, client=client2)
    gc.collect()
    set_values = []
    on_set.on_event(set_values.append)

    values = []
    value = await client.state_observe("test_state4", values.append)
    assert value == Unknown if initial_value is NoValue else initial_value

    # can set state from Value
    v.value = 6
    await asyncio.sleep(0.5)
    assert values == [6]

    # can set Value from state, causing an event
    await client.set("test_state4", 7)
    await asyncio.sleep(0.5)
    # no change
    assert v.value == 6
    assert values == [6]
    # event
    assert set_values == [7]


@pytest.mark.needs_server
async def test_action(client, client2):
    action = Mock()
    action.return_value = None
    await client.action_register("test_action", action)

    a1 = Value()
    a2 = Value()
    await action_call("test_action", a1, a2, client=client2)
    gc.collect()
    await asyncio.sleep(0.5)
    assert not action.called

    a1.value = 5
    await asyncio.sleep(0.5)
    assert not action.called

    a2.value = 6
    await asyncio.sleep(0.5)
    assert action.mock_calls == [call(5, 6)]

    a1.value = 7
    await asyncio.sleep(0.5)
    assert action.mock_calls == [call(5, 6), call(7, 6)]


@pytest.mark.needs_server
async def test_action_event(client, client2):
    action = Mock()
    action.return_value = None
    await client.action_register("test_action", action)

    e = Event()
    await action_call("test_action", e, client=client2)
    gc.collect()
    await asyncio.sleep(0.5)
    assert not action.called

    e.emit(5)
    await asyncio.sleep(0.5)
    assert action.mock_calls == [call(5)]


@pytest.mark.needs_server
async def test_set_value_no_initial(client, client2):
    set_callback = Mock()
    set_callback.return_value = None
    await client.state_register("test_state5", set_callback=set_callback)

    v = Value()
    await set_value("test_state5", v, client=client2)
    gc.collect()
    await asyncio.sleep(0.5)
    assert not set_callback.called

    v.value = 5
    await asyncio.sleep(0.5)
    assert set_callback.mock_calls == [call(5)]


@pytest.mark.needs_server
async def test_set_value_initial(client, client2):
    set_callback = Mock()
    set_callback.return_value = None
    await client.state_register("test_state6", set_callback=set_callback)

    v = Value(4)
    await set_value("test_state6", v, client=client2)
    gc.collect()
    await asyncio.sleep(0.5)
    assert set_callback.mock_calls == [call(4)]
    set_callback.reset_mock()

    v.value = 5
    await asyncio.sleep(0.5)
    assert set_callback.mock_calls == [call(5)]


@pytest.mark.needs_server
async def test_set_event(client, client2):
    set_callback = Mock()
    set_callback.return_value = None
    await client.state_register("test_state7", set_callback=set_callback)

    e = Event()
    await set_value("test_state7", e, client=client2)
    gc.collect()
    await asyncio.sleep(0.5)
    assert not set_callback.called

    e.emit(5)
    await asyncio.sleep(0.5)
    assert set_callback.mock_calls == [call(5)]


def test_replace_unknown():
    v = Value(Unknown)
    v_rep = replace_unknown(v, 0)
    assert v_rep.value == 0

    v.value = 5
    assert v_rep.value == 5
