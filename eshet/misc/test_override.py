from yarp import Value
import asyncio
import gc
import pytest
from ..client import Client
from ..exceptions import ErrorValue
import logging
from .override import override


@pytest.fixture
async def client():
    c = Client(
        base="/test_client_yoverride",
        logger=logging.getLogger("client"),
    )
    await c.wait_for_connection()

    yield c

    await c.close()


@pytest.mark.needs_server
async def test_override(client):
    def validate(x):
        if not isinstance(x, bool):
            raise ValueError(f"value must be a bool, not {x}")

    before = Value(True)
    after = await override("/test_override", before, validate=validate, client=client)
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
