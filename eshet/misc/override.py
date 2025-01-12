import asyncio
from eshet.yarp import get_default_eshet_client, state_register
from yarp import Value, fn, no_repeat
from yarp.temporal import emit_at


def validate_any(_value):
    pass


async def override(path, value: Value, *, validate=validate_any, client=None):
    """make an ESHET interface for overriding the given input value; returns a
    new value with the override applied

    the following paths are created:

    - action path/clear(): cancel the current override
    - action path/forever(value): override forever with value
    - action path/for(time, value): override for time seconds with value
    - state path/state: the current state of the override

    validate will be called with the value when setting the override, and
    should raise an exception if the value is not valid
    """
    loop = asyncio.get_event_loop()
    if client is None:
        client = await get_default_eshet_client()

    state = Value("off")
    await state_register(path + "/state", state, client=client)

    def clear():
        state.value = "off"

    await client.action_register(path + "/clear", clear)

    def forever(value):
        validate(value)
        state.value = "forever", value

    await client.action_register(path + "/forever", forever)

    def ovr_for(time, value):
        validate(value)
        state.value = "for", time, value

    await client.action_register(path + "/for", ovr_for)

    @fn
    def get_timeout(state):
        match state:
            case ("for", t, _):
                return loop.time() + t

    timeout = emit_at(get_timeout(state))

    @timeout.on_event
    def on_timeout(_):
        state.value = "off"

    state.add_input(timeout)

    @fn
    def clean_state(state):
        match state:
            case "off":
                return "off"
            case ("forever", v):
                return "override", v
            case ("for", _, v):
                return "override", v
            case _:
                assert False

    state_clean = no_repeat(clean_state(state))

    @fn
    def get_out(value, state):
        match state:
            case "off":
                return value
            case "override", v:
                return v
            case _:
                assert False

    return get_out(value, state_clean)
