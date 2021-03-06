import asyncio
from .messages import ServerMessage, MessageType
from .types import ResultType
import os
from inspect import isawaitable
from pathlib import PurePosixPath as Path
from collections import defaultdict
from .exceptions import Disconnected
from .protocol import Proto, TimeoutConfig, ProtoMessage
import logging


async def _make_awaitable(x):
    if isawaitable(x):
        return await x
    else:
        return x


def _run_in_task_if_coroutine(x):
    if asyncio.iscoroutine(x):
        asyncio.create_task(x)


default_server = os.environ.get("ESHET_SERVER", "localhost")


class Client:
    def __init__(
        self,
        base="/",
        server=default_server,
        client_id=None,
        timeout_cfg=TimeoutConfig(),
        logger=logging.getLogger("eshet.client"),
    ):
        self.base = Path(base)
        if not self.base.is_absolute():
            raise ValueError("base path must be absolute")
        self.client_id = client_id
        self.timeout_cfg = timeout_cfg
        self.logger = logger

        self.host, _sep, port_s = server.partition(":")
        self.port = 11236 if port_s == "" else int(port_s)

        self.protocol = None

        # are we currently connected to the server?
        self.connection_event = asyncio.Event()

        # callbacks for registered things
        self.actions = {}
        self.listens = defaultdict(list)

        # list of functions to call on re-connection
        self.registrations = []

        self.connection_task_handle = asyncio.create_task(
            self.__connection_task(), name="eshet connection"
        )

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
            await self.__connect_once()
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

    async def __handle_connection_events(self, queue):
        """handle events from a connection until it disconnects"""
        while True:
            match await queue.get():
                case (ProtoMessage.connected, new_id):
                    for registration in self.registrations:
                        await registration()
                    self.logger.info("connected")
                    self.client_id = new_id
                    self.connection_event.set()
                case (ProtoMessage.message, msg):
                    self.__handle_message(msg)
                case (ProtoMessage.disconnected,):
                    self.logger.error("disconnected")
                    await self.protocol.close()
                    self.protocol = None
                    self.connection_event.clear()
                    break

    def __handle_message(self, msg: ServerMessage):
        """handles messages after the handshake phase"""
        match msg:
            case (MessageType.action_call, reply_id, path, args):
                self.__wrap_call(reply_id, self.actions[path], *args)
            case (MessageType.event_notify, path, value):
                for cb in self.listens[path]:
                    _run_in_task_if_coroutine(cb(value))
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

        asyncio.create_task(task())

    @property
    def connected(self) -> bool:
        """are we currently connected?"""
        return self.connection_event.is_set()

    def wait_for_connection(self):
        """wait until the connection has been established"""
        return self.connection_event.wait()

    # utilities

    def __make_absolute(self, path: str) -> str:
        """get the absolute path for a path relative to base"""
        return str(self.base / path)

    def __check_connected(self):
        """throw if not connected"""
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
