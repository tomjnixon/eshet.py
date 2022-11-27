from enum import Enum, auto
from typing import Literal, Union
import msgpack
import struct
from .types import Result, ResultType, StateValueType, Msgpack, StateValue, ID, Path


class MessageType(Enum):
    hello = auto()
    hello_id = auto()

    reply = auto()
    reply_state = auto()

    ping = auto()

    action_register = auto()
    action_call = auto()

    prop_register = auto()
    prop_get = auto()
    prop_set = auto()

    get = auto()
    set = auto()

    event_register = auto()
    event_emit = auto()
    event_listen = auto()
    event_notify = auto()

    state_register = auto()
    state_changed = auto()
    state_unknown = auto()
    state_observe = auto()


EitherMessage = Union[
    tuple[Literal[MessageType.reply], ID, Result],
    tuple[Literal[MessageType.action_call], ID, Path, Msgpack],
]

ClientMessage = Union[
    EitherMessage,
    tuple[Literal[MessageType.hello], int, int],
    tuple[Literal[MessageType.hello_id], int, int, Msgpack],
    tuple[Literal[MessageType.reply_state], ID, StateValue],
    tuple[Literal[MessageType.ping], ID],
    tuple[Literal[MessageType.action_register], ID, Path],
    tuple[Literal[MessageType.prop_register], ID, Path],
    tuple[Literal[MessageType.get], ID, Path],
    tuple[Literal[MessageType.set], ID, Path, Msgpack],
    tuple[Literal[MessageType.event_register], ID, Path],
    tuple[Literal[MessageType.event_emit], ID, Path, Msgpack],
    tuple[Literal[MessageType.event_listen], ID, Path],
    tuple[Literal[MessageType.state_register], ID, Path],
    tuple[Literal[MessageType.state_changed], ID, Path, Msgpack],
    tuple[Literal[MessageType.state_unknown], ID, Path],
    tuple[Literal[MessageType.state_observe], ID, Path, Msgpack],
]

ServerMessage = Union[
    EitherMessage,
    tuple[Literal[MessageType.hello]],
    tuple[Literal[MessageType.hello_id], Msgpack],
    tuple[Literal[MessageType.prop_get], ID, Path],
    tuple[Literal[MessageType.prop_set], ID, Path, Msgpack],
    tuple[Literal[MessageType.event_notify], Path, Msgpack],
    tuple[Literal[MessageType.state_changed], Path, StateValue],
]

AnyMessage = Union[ClientMessage, ServerMessage]


def pack(obj):
    return msgpack.packb(obj, use_single_float=True)


def pack_path(path):
    return path.encode("ascii") + b"\0"


def pack_msg(msg: AnyMessage):
    match msg:
        case (MessageType.hello, version, timeout):
            return struct.pack(">BBH", 0x1, version, timeout)
        case (MessageType.hello_id, version, timeout, client_id):
            return struct.pack(">BBH", 0x2, version, timeout) + pack(client_id)

        case (MessageType.hello,):
            return struct.pack(">B", 0x3)
        case (MessageType.hello_id, client_id):
            return struct.pack(">B", 0x4) + pack(client_id)

        case (MessageType.reply, id, (ResultType.ok, value)):
            return struct.pack(">BH", 0x5, id) + pack(value)
        case (MessageType.reply, id, (ResultType.error, value)):
            return struct.pack(">BH", 0x6, id) + pack(value)

        case (MessageType.reply_state, id, (StateValueType.known, value)):
            return struct.pack(">BH", 0x7, id) + pack(value)
        case (MessageType.reply_state, id, StateValueType.unknown):
            return struct.pack(">BH", 0x8, id)

        case (MessageType.ping, id):
            return struct.pack(">BH", 0x9, id)

        case (MessageType.action_register, id, path):
            return struct.pack(">BH", 0x10, id) + pack_path(path)
        case (MessageType.action_call, id, path, args):
            return struct.pack(">BH", 0x11, id) + pack_path(path) + pack(args)

        case (MessageType.prop_register, id, path):
            return struct.pack(">BH", 0x20, id) + pack_path(path)
        case (MessageType.prop_get, id, path):
            return struct.pack(">BH", 0x21, id) + pack_path(path)
        case (MessageType.prop_set, id, path, value):
            return struct.pack(">BH", 0x22, id) + pack_path(path) + pack(value)
        case (MessageType.get, id, path):
            return struct.pack(">BH", 0x23, id) + pack_path(path)
        case (MessageType.set, id, path, value):
            return struct.pack(">BH", 0x24, id) + pack_path(path) + pack(value)

        case (MessageType.event_register, id, path):
            return struct.pack(">BH", 0x30, id) + pack_path(path)
        case (MessageType.event_emit, id, path, value):
            return struct.pack(">BH", 0x31, id) + pack_path(path) + pack(value)
        case (MessageType.event_listen, id, path):
            return struct.pack(">BH", 0x32, id) + pack_path(path)
        case (MessageType.event_notify, path, value):
            return struct.pack(">B", 0x33) + pack_path(path) + pack(value)

        case (MessageType.state_register, id, path):
            return struct.pack(">BH", 0x40, id) + pack_path(path)
        case (MessageType.state_changed, id, path, state):
            return struct.pack(">BH", 0x41, id) + pack_path(path) + pack(state)
        case (MessageType.state_unknown, id, path):
            return struct.pack(">BH", 0x42, id) + pack_path(path)
        case (MessageType.state_observe, id, path):
            return struct.pack(">BH", 0x43, id) + pack_path(path)
        case (MessageType.state_changed, path, (StateValueType.known, state)):
            return struct.pack(">B", 0x44) + pack_path(path) + pack(state)
        case (MessageType.state_changed, path, StateValueType.unknown):
            return struct.pack(">B", 0x45) + pack_path(path)
        case _:
            assert False, "unknown message"


def unpack_msg(msg):
    pos = 0

    def read(fmt):
        nonlocal pos
        res = struct.unpack_from(fmt, msg, pos)
        pos += struct.calcsize(fmt)
        return res if len(res) > 1 else res[0]

    def read_path():
        nonlocal pos
        term = msg.index(0, pos)
        res = msg[pos:term].decode("ascii")
        pos = term + 1
        return res

    def read_pack():
        nonlocal pos
        res = msgpack.loads(msg[pos:])
        pos = len(msg)
        return res

    msg_type = read("B")

    match msg_type:
        case 0x01:
            version, timeout = read(">BH")
            return (MessageType.hello, version, timeout)
        case 0x02:
            version, timeout = read(">BH")
            return (MessageType.hello_id, version, timeout, read_pack())
        case 0x03:
            return (MessageType.hello,)
        case 0x04:
            return (MessageType.hello_id, read_pack())
        case 0x05:
            return (MessageType.reply, read(">H"), (ResultType.ok, read_pack()))
        case 0x06:
            return (MessageType.reply, read(">H"), (ResultType.error, read_pack()))
        case 0x07:
            return (
                MessageType.reply_state,
                read(">H"),
                (StateValueType.known, read_pack()),
            )
        case 0x08:
            return (
                MessageType.reply_state,
                read(">H"),
                StateValueType.unknown,
            )
        case 0x09:
            return (MessageType.ping, read(">H"))
        case 0x10:
            return (MessageType.action_register, read(">H"), read_path())
        case 0x11:
            return (MessageType.action_call, read(">H"), read_path(), read_pack())
        case 0x20:
            return (MessageType.prop_register, read(">H"), read_path())
        case 0x21:
            return (MessageType.prop_get, read(">H"), read_path())
        case 0x22:
            return (MessageType.prop_set, read(">H"), read_path(), read_pack())
        case 0x23:
            return (MessageType.get, read(">H"), read_path())
        case 0x24:
            return (MessageType.set, read(">H"), read_path(), read_pack())
        case 0x30:
            return (MessageType.event_register, read(">H"), read_path())
        case 0x31:
            return (MessageType.event_emit, read(">H"), read_path(), read_pack())
        case 0x32:
            return (MessageType.event_listen, read(">H"), read_path())
        case 0x33:
            return (MessageType.event_notify, read_path(), read_pack())
        case 0x40:
            return (MessageType.state_register, read(">H"), read_path())
        case 0x41:
            return (MessageType.state_changed, read(">H"), read_path(), read_pack())
        case 0x42:
            return (MessageType.state_unknown, read(">H"), read_path())
        case 0x43:
            return (MessageType.state_observe, read(">H"), read_path())
        case 0x44:
            return (
                MessageType.state_changed,
                read_path(),
                (StateValueType.known, read_pack()),
            )
        case 0x45:
            return (
                MessageType.state_changed,
                read_path(),
                StateValueType.unknown,
            )
        case _:
            raise ValueError("could not parse message")


def test_pack_unpack():
    messages = [
        (MessageType.hello,),
        (MessageType.hello, 1, 30),
        (MessageType.hello_id, b"foo"),
        (MessageType.hello_id, 1, 30, b"foo"),
        (MessageType.reply, 42, (ResultType.ok, 5)),
        (MessageType.reply, 42, (ResultType.error, 5)),
        (MessageType.reply_state, 42, (StateValueType.known, [b"foo", 5])),
        (MessageType.reply_state, 42, StateValueType.unknown),
        (MessageType.ping, 42),
        (MessageType.action_register, 42, "/path"),
        (MessageType.action_call, 42, "/path", [b"foo", 5]),
        (MessageType.prop_register, 42, "/path"),
        (MessageType.prop_get, 42, "/path"),
        (MessageType.prop_set, 42, "/path", [b"foo", 5]),
        (MessageType.get, 42, "/path"),
        (MessageType.set, 42, "/path", [b"foo", 5]),
        (MessageType.event_register, 42, "/path"),
        (MessageType.event_emit, 42, "/path", [b"foo", 5]),
        (MessageType.event_listen, 42, "/path"),
        (MessageType.event_notify, "/path", [b"foo", 5]),
        (MessageType.state_register, 42, "/path"),
        (MessageType.state_changed, 42, "/path", [b"foo", 5]),
        (MessageType.state_unknown, 42, "/path"),
        (MessageType.state_observe, 42, "/path"),
        (MessageType.state_changed, "/path", (StateValueType.known, [b"foo", 5])),
        (MessageType.state_changed, "/path", StateValueType.unknown),
    ]

    for message in messages:
        packed = pack_msg(message)
        unpacked = unpack_msg(packed)
        assert unpacked == message
