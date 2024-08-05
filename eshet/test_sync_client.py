from . import Unknown
from .sync_client import SyncClient
import pytest
import logging


@pytest.fixture
async def client():
    c = SyncClient(
        base="/test_client",
        logger=logging.getLogger("client"),
    )
    c.wait_for_connection().result()

    yield c

    c.close()


@pytest.mark.needs_server
def test_action(client):
    # also tests generic wrappers
    client.action_register("action", lambda x: x + 1).result()

    assert client.action_call("action", 5).result() == 6


@pytest.mark.needs_server
def test_state_queue(client):
    state = client.state_register("state").result()

    q = client.state_observe_queue("state").result()

    assert q.get_nowait() is Unknown

    state.changed(5).result()
    assert q.get() == 5

    state.unknown().result()
    assert q.get() is Unknown

    assert q.empty()


@pytest.mark.needs_server
def test_state_wrapper(client):
    state = client.state_register("state").result()

    w = client.state_observe_wrapper("state").result()

    assert w.get_value() is Unknown

    state.changed(5).result()
    while not w.changed:
        pass  # pragma: no cover
    assert w.get_value() == 5
    assert not w.changed

    state.unknown().result()
    while not w.changed:
        pass  # pragma: no cover
    assert w.get_value() is Unknown
    assert not w.changed


@pytest.mark.needs_server
def test_event_listen_queue(client):
    ev = client.event_register("event").result()

    q = client.event_listen_queue("event").result()
    assert q.empty()

    ev(5).result()
    assert q.get() == 5
