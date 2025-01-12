import asyncio
from eshet.yarp import get_default_eshet_client, state_register
from yarp import Value, fn, no_repeat
from yarp.store import null_store
from yarp.temporal import emit_at


def validate_any(_value):
    pass


async def override(
    path, value: Value, *, validate=validate_any, store_cfg=null_store, client=None
):
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

    # state can be:
    # "off": pass-through
    # ("forever", value): override to value
    # ("for", start, t, value): override to value starting at start and ending
    #   at start+t

    def validate_state(old_state):
        match old_state:
            case "off":
                pass
            case ("forever", v):
                validate(v)
            case ("for", float(), float(), v):
                validate(v)
            case _:
                assert False

    state = store_cfg.build_value("off", validate=validate_state)

    def clear():
        state.value = "off"

    await client.action_register(path + "/clear", clear)

    def forever(value):
        validate(value)
        state.value = "forever", value

    await client.action_register(path + "/forever", forever)

    def ovr_for(time, value):
        validate(value)
        state.value = "for", loop.time(), time, value

    await client.action_register(path + "/for", ovr_for)

    @fn
    def get_timeout(state):
        match state:
            case ("for", start, t, _):
                return start + t

    timeout = get_timeout(state)

    # XXX: make sure that a timeout that happened while this was not running is
    # not visible to the user. this should really be handled by a callback_at
    # function, which wouldn't have to delay the first callback to the next
    # loop
    if timeout.value is not None and timeout.value < loop.time():
        state.value = "off"

    timeout_event = emit_at(timeout)

    @timeout_event.on_event
    def on_timeout(_):
        state.value = "off"

    state.add_input(timeout_event)

    await state_register(path + "/state", state, client=client)

    @fn
    def clean_state(state):
        match state:
            case "off":
                return "off"
            case ("forever", v):
                return "override", v
            case ("for", _, _, v):
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
