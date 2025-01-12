from yarp import Value
from yarp.store import FakeStoreConfig
import asyncio
import gc
import pytest
from ..client import Client
from ..exceptions import ErrorValue
import logging
from .override import override
from copy import deepcopy


@pytest.fixture
async def client():
    c = Client(
        base="/test_client_yoverride",
        logger=logging.getLogger("client"),
    )
    await c.wait_for_connection()

    yield c

    await c.close()


def validate_bool(x):
    if not isinstance(x, bool):
        raise ValueError(f"value must be a bool, not {x}")


@pytest.mark.needs_server
async def test_override(client):

    before = Value(True)
    after = await override(
        "/test_override", before, validate=validate_bool, client=client
    )
    gc.collect()

    assert after.value is True

    before.value = False
    assert after.value is False

    # clear has no effect
    await client.action_call("/test_override/clear")
    assert after.value is False

    # forever
    await client.action_call("/test_override/forever", True)
    assert after.value is True
    await client.action_call("/test_override/clear")
    assert after.value is False

    # for auto-clear
    await client.action_call("/test_override/for", 0.2, True)
    assert after.value is True
    await asyncio.sleep(0.4)
    assert after.value is False

    # for manual clear
    await client.action_call("/test_override/for", 0.4, True)
    assert after.value is True
    await asyncio.sleep(0.2)
    await client.action_call("/test_override/clear")
    assert after.value is False
    await asyncio.sleep(0.4)
    assert after.value is False

    with pytest.raises(ErrorValue):
        await client.action_call("/test_override/forever", 5)
    assert after.value is False


@pytest.mark.needs_server
async def test_store(client):
    store = FakeStoreConfig()

    before = Value(True)
    after = await override(
        "/test_override2",
        before,
        validate=validate_bool,
        client=client,
        store_cfg=store,
    )

    assert after.value is True
    await client.action_call("/test_override2/for", 0.3, False)
    assert after.value is False

    await asyncio.sleep(0.2)

    # another override built from a copy of the store behaves as we'd expect the original to

    store2 = deepcopy(store)
    after2 = await override(
        "/test_override3",
        before,
        validate=validate_bool,
        client=client,
        store_cfg=store2,
    )
    assert after2.value is False

    await asyncio.sleep(0.2)

    assert after2.value is True

    # state is saved on timeout

    store3 = deepcopy(store2)
    after3 = await override(
        "/test_override4",
        before,
        validate=validate_bool,
        client=client,
        store_cfg=store3,
    )
    assert after3.value is True


@pytest.mark.needs_server
async def test_store_expire(client):
    store = FakeStoreConfig()

    before = Value(True)
    after = await override(
        "/test_override5",
        before,
        validate=validate_bool,
        client=client,
        store_cfg=store,
    )

    assert after.value is True
    await client.action_call("/test_override5/for", 0.1, False)
    assert after.value is False

    # check that if the override expires while not running, the old value is
    # not visible to the user

    store2 = deepcopy(store)

    await asyncio.sleep(0.2)

    after2 = await override(
        "/test_override6",
        before,
        validate=validate_bool,
        client=client,
        store_cfg=store2,
    )
    assert after2.value is True
