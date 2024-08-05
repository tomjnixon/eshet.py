import eshet
import asyncio
import threading
from queue import Queue
from dataclasses import dataclass
from concurrent.futures import Future


class SyncClient:
    """non-async wrapper around eshet.Client

    This runs an asyncio event loop on an internal thread.

    Most methods return a Future with the value of the matching method of
    eshet.Client. If you want to wait for the action to complete, or get the
    result, call .result() on it.
    """

    def __init__(self, *args, **kwargs):
        self.loop = loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        self.thread = threading.Thread(target=run_loop)
        self.thread.start()

        async def make_client():
            return eshet.Client(*args, **kwargs)

        self.client = self.run_coro(make_client()).result()

    def close(self):
        """stop and join the internal thread"""
        self.run_coro(self.client.close()).result()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join()

    def run_coro(self, coro) -> Future:
        """run a given coroutine on the internal thread."""
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def state_observe_queue(self, path) -> Future[Queue]:
        """observe a state, pushing changes (and the initial value) to a queue"""

        async def setup():
            q = Queue()
            q.put_nowait(await self.client.state_observe(path, q.put_nowait))
            return q

        return self.run_coro(setup())

    class StateObserveWrapper:
        """represents the value of an observed state, which is updated in the
        background
        """

        def __init__(self):
            self.lock = threading.Lock()
            self._value = eshet.Unknown
            self._changed = False

        @property
        def changed(self):
            """has the value changed since the last call to get_value"""
            with self.lock:
                changed_copy = self._changed
            return changed_copy

        def get_value(self):
            """get the value, and clear the changed flag"""
            with self.lock:
                value_ref = self._value
                self._changed = False
            return value_ref

        def _set_value(self, value):
            with self.lock:
                self._value = value
                self._changed = True

    def state_observe_wrapper(self, path) -> Future[StateObserveWrapper]:
        """observe a state, returning a wrapper containing the value that is
        updated as the state changes
        """

        async def setup():
            wrapper = self.StateObserveWrapper()
            wrapper._set_value(
                await self.client.state_observe(path, wrapper._set_value)
            )
            return wrapper

        return self.run_coro(setup())

    @dataclass
    class StateWrapper:
        """wrapper around registered states which just stores a client and a path"""

        client: "SyncClient"
        path: str

        def changed(self, value) -> Future:
            """update the value of the state"""
            return self.client.state_changed(self.path, value)

        def unknown(self) -> Future:
            """update the value of the state"""
            return self.client.state_unknown(self.path)

    def state_register(self, path, set_callback=None) -> Future[StateWrapper]:
        """register a state"""

        async def register():
            async_wrapper = await self.client.state_register(
                path, set_callback=set_callback
            )
            return self.StateWrapper(self, async_wrapper.path)

        return self.run_coro(register())

    def event_listen_queue(self, path) -> Future[Queue]:
        """listen to an event, pushing the values to a queue"""

        async def register():
            q = Queue()
            await self.client.event_listen_cb(path, q.put_nowait)
            return q

        return self.run_coro(register())

    def event_register(self, path):
        """register an event; returns an callable which emits an event
        given a payload (and returns a Future)
        """

        async def register():
            cb = await self.client.event_register(path)

            def cb_wrapper(value):
                return self.run_coro(cb(value))

            return cb_wrapper

        return self.run_coro(register())

    @staticmethod
    def _make_wrapper(name):
        from functools import wraps

        meth = getattr(eshet.Client, name)

        @wraps(meth)
        def wrapper(self, *args, **kwargs):
            return self.run_coro(meth(self.client, *args, **kwargs))

        return wrapper

    action_call = _make_wrapper("action_call")
    action_register = _make_wrapper("action_register")
    event_listen_cb = _make_wrapper("event_listen_cb")
    get = _make_wrapper("get")
    set = _make_wrapper("set")
    state_changed = _make_wrapper("state_changed")
    state_observe = _make_wrapper("state_observe")
    state_unknown = _make_wrapper("state_unknown")
    wait_for_connection = _make_wrapper("wait_for_connection")

    # not wrapped:
    # event_listen returns async generator
