import yarp
from .client import Client, Unknown
from .utils import in_task, TaskStrategy, RunInTask


_default_client = None


def set_default_eshet_client(client):
    global _default_client
    _default_client = client


async def get_default_eshet_client():
    global _default_client
    if _default_client is None:
        _default_client = Client()
        await _default_client.wait_for_connection()
    return _default_client


async def event_listen(path, client=None):
    """make an instantaneous Value which is set whenever the given event
    fires
    """
    if client is None:
        client = await get_default_eshet_client()

    output_value = yarp.Value()
    await client.event_listen_cb(path, output_value.set_instantaneous_value)
    return output_value


async def state_observe(path, client=None):
    """make a continuous Value which has the value of the given state

    the value will be set by the time this returns, and will be set to
    client.Unknown if the state is unknown. it will therefore never be NoValue.
    """
    if client is None:
        client = await get_default_eshet_client()

    output_value = yarp.Value()

    def cb(value):
        output_value.value = value

    state = await client.state_observe(path, cb)

    output_value.value = state

    return output_value


async def state_register(path, value, client=None, settable=False):
    """register a state which has the same value as `value`

    if settable, a set callback is registered which sets the value

    client.Unknown and yarp.NoValue are both mapped to unknown
    """
    if client is None:
        client = await get_default_eshet_client()
    value = yarp.ensure_value(value)

    if settable:

        def set_callback(new_value):
            value.value = new_value

        state = await client.state_register(path, set_callback=set_callback)
    else:
        state = await client.state_register(path)

    async def send(value):
        if value is Unknown:
            await state.unknown()
        elif value is yarp.NoValue:
            await state.unknown()
        else:
            await state.changed(value)

    value.on_value_changed(in_task(send))

    await send(value.value)


def contains_novalue_uknonwn(value):
    """does a value contain NoValue or Unknown somewhere?"""
    if value is yarp.NoValue:
        return True
    elif value is Unknown:
        return True

    elif isinstance(value, (list, tuple, set)):
        return any(contains_novalue_uknonwn(v) for v in value)
    elif isinstance(value, dict):
        return any(
            contains_novalue_uknonwn(k) or contains_novalue_uknonwn(v)
            for k, v in value.items()
        )
    else:
        return False


async def action_call(
    path,
    *args,
    client=None,
    strategy: TaskStrategy = RunInTask(),
):
    """call an action whenever args does not contain NoValue/Unknown"""
    if client is None:
        client = await get_default_eshet_client()
    args = yarp.ensure_value(args)

    @args.on_value_changed
    @strategy.wrap_fn
    async def cb(args_value):
        if not contains_novalue_uknonwn(args_value):
            await client.action_call(path, *args_value)

    cb(args.value)
