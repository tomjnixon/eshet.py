import struct
from enum import Enum, auto
import asyncio
from dataclasses import dataclass
from typing import Tuple
from .messages import pack_msg, unpack_msg, ClientMessage, ServerMessage, MessageType
from .types import ResultType
from .exceptions import ErrorValue, Disconnected

header_fmt = ">BH"
header_len = struct.calcsize(header_fmt)
sync_word = 0x47


class ProtoState(Enum):
    init = auto()
    sent_hello = auto()
    connected = auto()
    disconnected = auto()


class ProtoMessage(Enum):
    """message types from protocol to client"""

    # connection made and hello done. argument: new id
    connected = auto()
    # a message was received. argument: the message
    message = auto()
    # connection was disconnected
    disconnected = auto()


@dataclass
class TimeoutConfig:
    """configuration for protocol-level timeouts"""

    # send a ping if we haven't sent anything for this long
    idle_ping: int = 15
    # tell the server to time out if it hasn't received a message for this long;
    # must be more than idle_ping
    server_timeout: int = 30
    # how long to wait for a ping before assuming the connection is dead
    ping_timeout: int = 5


class Proto(asyncio.Protocol):
    def __init__(self, message_callback, timeout_cfg, client_id, logger):
        self.message_callback = message_callback
        self.timeout_cfg = timeout_cfg
        self.client_id = client_id
        self.logger = logger

        self.transport = None
        self.buffer = bytearray()

        self.state = ProtoState.init

        self.reply_ids = {}
        self.next_id = 0

        self.last_send = None
        self.ping_task_handle = None

    async def ping_task(self):
        loop = asyncio.get_running_loop()
        while True:
            await asyncio.sleep(1)
            if self.state == ProtoState.disconnected:
                break
            if loop.time() >= self.last_send + self.timeout_cfg.idle_ping:
                ping_id, future = self.get_id()
                self.send_message_internal((MessageType.ping, ping_id))
                try:
                    await asyncio.wait_for(future, self.timeout_cfg.ping_timeout)
                except asyncio.TimeoutError:
                    self.logger.error("ping timed out")
                    self.transport.close()
                    break

    def connection_made(self, transport):
        self.transport = transport
        self.send_hello()
        self.state = ProtoState.sent_hello

    def send_hello(self):
        if self.client_id is None:
            self.send_message_internal(
                (MessageType.hello, 1, self.timeout_cfg.server_timeout)
            )
        else:
            self.send_message_internal(
                (
                    MessageType.hello_id,
                    1,
                    self.timeout_cfg.server_timeout,
                    self.client_id,
                )
            )

    def data_received(self, data):
        self.buffer.extend(data)

        pos = 0
        while True:
            if pos + header_len > len(self.buffer):
                break

            sync, msg_len = struct.unpack_from(header_fmt, self.buffer, pos)

            if sync != sync_word:
                raise ValueError("expected sync word")

            if pos + header_len + msg_len > len(self.buffer):
                break

            msg = unpack_msg(self.buffer[pos + header_len : pos + header_len + msg_len])
            self.handle_message(msg)

            pos += header_len + msg_len

        self.buffer = self.buffer[pos:]

    def handle_message(self, msg: ServerMessage):
        self.logger.debug(f"recv {msg}")

        match self.state:
            case ProtoState.sent_hello:
                self.handle_hello_message(msg)
            case ProtoState.connected:
                self.handle_normal_message(msg)

    def handle_hello_message(self, msg: ServerMessage):
        """handles messages during the handshake phase"""
        match msg:
            case (MessageType.hello_id, new_id):
                self.message_callback((ProtoMessage.connected, new_id))
            case (MessageType.hello,):
                self.message_callback((ProtoMessage.connected, self.client_id))
            case _:
                raise Exception(f"unexpected message: {msg}")

        self.state = ProtoState.connected
        self.ping_task_handle = asyncio.create_task(self.ping_task(), name="ping")

    def handle_normal_message(self, msg: ServerMessage):
        """handles messages after the handshake phase"""
        match msg:
            case (MessageType.reply, reply_id, (ResultType.ok, value)):
                self.reply_ids.pop(reply_id).set_result(value)
            case (MessageType.reply_state, reply_id, value):
                self.reply_ids.pop(reply_id).set_result(value)
            case (MessageType.reply, reply_id, (ResultType.error, value)):
                self.reply_ids.pop(reply_id).set_exception(ErrorValue(value))
            case _:
                self.message_callback((ProtoMessage.message, msg))

    def connection_lost(self, exc):
        # is this necessary?
        self.transport.close()

        if self.state != ProtoState.disconnected:
            self.state = ProtoState.disconnected
            for future in self.reply_ids.values():
                # futures may be canceled by client code, for example if they
                # use wait_for (like ping uses above)
                if not future.done():
                    future.set_exception(Disconnected())
            self.message_callback((ProtoMessage.disconnected,))

    async def close(self):
        self.transport.close()

        if self.ping_task_handle is not None:
            self.ping_task_handle.cancel()
            try:
                await self.ping_task_handle
            except asyncio.CancelledError:
                pass
            self.ping_task_handle = None

    def send_message(self, msg: ClientMessage):
        if self.state != ProtoState.connected:
            raise Disconnected()
        self.send_message_internal(msg)

    def send_message_internal(self, msg: ClientMessage):
        self.logger.debug(f"send {msg}")
        packed = pack_msg(msg)
        self.transport.write(struct.pack(header_fmt, sync_word, len(packed)) + packed)
        self.last_send = asyncio.get_running_loop().time()

    def get_id(self) -> Tuple[int, asyncio.Future]:
        while self.next_id in self.reply_ids:
            self.next_id = (self.next_id + 1) & 0xFFFF

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.reply_ids[self.next_id] = future

        return self.next_id, future
