import asyncio
import yarp
from .client import Client, Unknown


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

    @value.on_value_changed
    def cb(value):
        asyncio.create_task(send(value))

    await send(value.value)
