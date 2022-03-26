from typing import Literal, Any, Union
from enum import Enum, auto


class ResultType(Enum):
    ok = auto()
    error = auto()


class StateValueType(Enum):
    known = auto()
    unknown = auto()


Msgpack = Any

Result = tuple[ResultType, Msgpack]

StateValue = Union[
    tuple[Literal[StateValueType.known], Msgpack],
    Literal[StateValueType.known],
]

ID = int
Path = str
