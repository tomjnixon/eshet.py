import asyncio
from dataclasses import dataclass
from .messages import ServerMessage, MessageType
from .types import ResultType, StateValueType
import os
from inspect import isawaitable
from pathlib import PurePosixPath as Path
from collections import defaultdict
from .exceptions import Disconnected
from .protocol import Proto, TimeoutConfig, ProtoMessage
from .utils import create_task_in_set
import logging
import sentinel


async def _make_awaitable(x):
    if isawaitable(x):
        return await x
    else:
        return x


# for states; this is a bit easier to work with in python than the
# '{known, X} | unknown' representation in erlang
Unknown = sentinel.create(
    "Unknown",
    cls_dict=dict(
        __bool__=(lambda self: False),
    ),
)


def to_Unknown(known_unknown):
    match known_unknown:
        case (StateValueType.known, value):
            return value
        case StateValueType.unknown:
            return Unknown


class Client:
    """ESHET client"""

    def __init__(
        self,
        base: str = "/",
        server: str = None,
        client_id=None,
        timeout_cfg: TimeoutConfig = TimeoutConfig(),
        logger=logging.getLogger("eshet.client"),
    ):
        """
        Parameters:
            base: Base path for this client: relative paths passed to other
                functions will be relative to this.
            server: ESHET server to connect to; defaults to the `ESHET_SERVER`
                environment variable, or localhost. This may also include the port
                number (in the form host:port), which defaults to 11236.
            client_id: msgpack-serialisable ID for this client; will be allocated
                by the server if not provided
            timeout_cfg: configuration for protocol-level timeouts
            logger: logger for connection messages
        """
        self.base = Path(base)
        if not self.base.is_absolute():
            raise ValueError("base path must be absolute")
        self.client_id = client_id
        self.timeout_cfg = timeout_cfg
        self.logger = logger

        if server is None:
            server = os.environ.get("ESHET_SERVER", "localhost")
        self.host, _sep, port_s = server.partition(":")
        self.port = 11236 if port_s == "" else int(port_s)

        self.protocol = None

        # are we currently connected to the server?
        self.connection_event = asyncio.Event()

        # callbacks for registered things
        self.actions = {}
        self.listens = defaultdict(list)
        self.observes = defaultdict(list)
        self.states = {}

        # current values for registered states, for re-registration
        self.registered_state_values = {}
        # values of observed states, to be returned by state_observe
        # may be a future if the observe has not yet been registered
        self.observed_state_values = {}

        # list of functions to call on re-connection
        self.registrations = []

        self.connection_task_handle = asyncio.create_task(
            self.__connection_task(), name="eshet connection"
        )

        self.tasks = set()

    async def close(self):
        if self.connection_task_handle is not None:
            self.connection_task_handle.cancel()
            try:
                await self.connection_task_handle
            except asyncio.CancelledError:
                pass
            self.connection_task_handle = None

        if self.protocol is not None:
            await self.protocol.close()
            self.protocol = None

    # connection-handling stuff

    async def __connection_task(self):
        """task that repeatedly tries to open a connection, and handles
        messages from it
        """
        while True:
            try:
                await self.__connect_once()
            except Exception as e:
                self.logger.exception("error in connection task")
            await asyncio.sleep(1.0)

    async def __connect_once(self):
        """connect to the server once and handle events until disconnected or
        canceled
        """
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()

        self.logger.info("connecting")
        try:
            transport, self.protocol = await loop.create_connection(
                lambda: Proto(
                    queue.put_nowait, self.timeout_cfg, self.client_id, self.logger
                ),
                self.host,
                self.port,
            )
        except Exception as e:
            self.logger.error(f"error connecting: {e}")
        else:
            await self.__handle_connection_events(queue)

    async def __send_registrations(self):
        for registration in self.registrations:
            await registration()

        for path, value in self.registered_state_values.items():
            if value is not Unknown:
                id, future = self.protocol.get_id()
                self.protocol.send_message((MessageType.state_changed, id, path, value))
                await future

        for path in self.observed_state_values:
            id, future = self.protocol.get_id()
            self.protocol.send_message((MessageType.state_observe, id, path))
            self.__state_update(path, await future)

    async def __handle_connection_events(self, queue):
        """handle events from a connection until it disconnects"""
        while True:
            match await queue.get():
                case (ProtoMessage.connected, new_id):
                    await self.__send_registrations()
                    self.logger.info("connected")
                    self.client_id = new_id
                    self.connection_event.set()
                case (ProtoMessage.message, msg):
                    self.__handle_message(msg)
                case (ProtoMessage.disconnected,):
                    self.logger.error("disconnected")
                    await self.protocol.close()
                    self.protocol = None

                    for state, f in self.observed_state_values.items():
                        # if a disconnect happens during registration, avoid
                        # clients seeing unknown
                        if not asyncio.isfuture(f):
                            self.__state_update(state, StateValueType.unknown)

                    self.connection_event.clear()
                    break

    def __handle_message(self, msg: ServerMessage):
        """handles messages after the handshake phase"""
        match msg:
            case (MessageType.action_call, reply_id, path, args):
                self.__wrap_call(reply_id, self.actions[path], *args)
            case (MessageType.event_notify, path, value):
                for cb in self.listens[path]:
                    self.__run_in_task_if_coroutine(cb(value))
            case (MessageType.state_changed, path, known_unknown):
                self.__state_update(path, known_unknown)
            case (MessageType.state_set, reply_id, path, value):
                if path in self.states:
                    self.__wrap_call(reply_id, self.states[path], value)
                else:
                    self.protocol.send_message(
                        (
                            MessageType.reply,
                            reply_id,
                            (ResultType.error, "not_implemented"),
                        )
                    )
            case _:
                raise Exception(f"unexpected message: {msg}")

    def __wrap_call(self, reply_id, cb, *args):
        """call cb(*args) in a task and send the result with (reply, reply_id, ...)"""

        async def task():
            try:
                result = await _make_awaitable(cb(*args))
            except Exception as e:
                self.protocol.send_message(
                    (
                        MessageType.reply,
                        reply_id,
                        (ResultType.error, str(e)),
                    )
                )
            else:
                self.protocol.send_message(
                    (MessageType.reply, reply_id, (ResultType.ok, result))
                )

        create_task_in_set(self.tasks, task())

    @property
    def connected(self) -> bool:
        """are we currently connected?"""
        return self.connection_event.is_set()

    def wait_for_connection(self):
        """wait until the connection has been established"""
        return self.connection_event.wait()

    # utilities

    def __run_in_task_if_coroutine(self, x):
        """if x is a coroutine, run it in a task, saved in self.tasks"""
        if asyncio.iscoroutine(x):
            create_task_in_set(self.tasks, x)

    def __make_absolute(self, path: str) -> str:
        """get the absolute path for a path relative to base"""
        return str(self.base / path)

    def __check_connected(self):
        """raise if not connected"""
        if not self.connected:
            raise Disconnected()

    async def __do_registration(self, message, path):
        """register something by sending (message, id, path) now if connected,
        and on reconnection
        """

        async def register():
            id, future = self.protocol.get_id()
            self.protocol.send_message((message, id, path))
            await future

        self.registrations.append(register)
        if self.connected:
            await register()

    # actions

    async def action_register(self, path, callback):
        """register an action

        callback will be called with the action arguments to get the return
        value. if the return is awaitable, it will be awaited in a task
        """
        path = self.__make_absolute(path)
        self.actions[path] = callback
        await self.__do_registration(MessageType.action_register, path)

    async def action_call(self, path, *args):
        """call an action"""
        path = self.__make_absolute(path)
        self.__check_connected()
        id, future = self.protocol.get_id()
        self.protocol.send_message((MessageType.action_call, id, path, args))
        return await future

    # property/state actions

    async def get(self, path):
        """get a state or property"""
        path = self.__make_absolute(path)
        self.__check_connected()
        id, future = self.protocol.get_id()
        self.protocol.send_message((MessageType.get, id, path))
        return await future

    async def set(self, path, value):
        """set a state or property"""
        path = self.__make_absolute(path)
        self.__check_connected()
        id, future = self.protocol.get_id()
        self.protocol.send_message((MessageType.set, id, path, value))
        return await future

    # events

    async def event_register(self, path):
        """register an event; returns an async callable which emits an event
        given a payload
        """
        path = self.__make_absolute(path)

        async def emit(value=None):
            self.__check_connected()
            id, future = self.protocol.get_id()
            self.protocol.send_message((MessageType.event_emit, id, path, value))
            await future

        await self.__do_registration(MessageType.event_register, path)
        return emit

    async def event_listen_cb(self, path, callback):
        """listen for events; callback will be called with the payload

        if it returns a coroutine, it will be ran in a task
        """
        path = self.__make_absolute(path)
        self.listens[path].append(callback)
        if len(self.listens[path]) == 1:
            await self.__do_registration(MessageType.event_listen, path)

    async def event_listen(self, path):
        """listen for events; returns an async iterator of the payloads"""
        queue = asyncio.Queue()
        await self.event_listen_cb(path, queue.put_nowait)

        while True:
            yield await queue.get()

    # states

    @dataclass
    class StateWrapper:
        """wrapper around registered states which just stores a client and a path"""

        client: "Client"
        path: str

        async def changed(self, value):
            """update the value of the state; equivalent to :func:`Client.state_changed`"""
            return await self.client.state_changed(self.path, value)

        async def unknown(self):
            """update the value of the state; equivalent to :func:`Client.state_unknown`"""
            return await self.client.state_unknown(self.path)

    async def state_register(self, path, set_callback=None) -> StateWrapper:
        """register a state"""
        path = self.__make_absolute(path)
        self.registered_state_values[path] = Unknown
        if set_callback is not None:
            self.states[path] = set_callback
        await self.__do_registration(MessageType.state_register, path)
        return self.StateWrapper(self, path)

    async def state_changed(self, path, value):
        """update the value of a registered state

        if value is :data:`eshet.Unknown`, it is marked as unknown
        """
        if value is Unknown:
            return await self.state_unknown(path)

        path = self.__make_absolute(path)
        self.registered_state_values[path] = value
        self.__check_connected()
        id, future = self.protocol.get_id()
        self.protocol.send_message((MessageType.state_changed, id, path, value))
        await future

    async def state_unknown(self, path):
        """clear the value of a registered state"""
        path = self.__make_absolute(path)
        self.registered_state_values[path] = Unknown
        self.__check_connected()
        id, future = self.protocol.get_id()
        self.protocol.send_message((MessageType.state_unknown, id, path))
        await future

    async def state_observe(self, path, callback):
        """observe a state, returns the current value or Unknown, and calls callback
        with subsequent values"""
        # cases to consider:
        # - first call
        # - call while initial registration is ongoing
        #   - observed_state_values[path] is a future
        # - call after initial registration has returned
        #   - observed_state_values[path] is a value
        # - call while reconnecting
        #   - observed_state_values[path] is Unknown

        path = self.__make_absolute(path)
        if path in self.observed_state_values:
            value = await _make_awaitable(self.observed_state_values[path])
        else:
            loop = asyncio.get_running_loop()
            stored_future = loop.create_future()
            self.observed_state_values[path] = stored_future

            if self.connected:
                id, future = self.protocol.get_id()
                self.protocol.send_message((MessageType.state_observe, id, path))

                value = self.__state_update(path, await future)
            else:
                value = await stored_future

        self.observes[path].append(callback)
        return value

    def __state_update(self, path, known_unknown):
        # handle state updates for path, by resolving the future or calling
        # callbacks
        value = to_Unknown(known_unknown)

        f = self.observed_state_values[path]
        if asyncio.isfuture(f):
            f.set_result(value)
            self.observed_state_values[path] = value
        else:
            self.observed_state_values[path] = value
            for cb in self.observes[path]:
                self.__run_in_task_if_coroutine(cb(value))

        return value
