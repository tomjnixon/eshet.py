from eshet.yarp import state_observe, state_register_set_event, set_value
import asyncio


async def main(args):
    # get a Value corresponding to a state
    state = await state_observe(args.from_state)

    # register a new state with a modified value, and get an Event which emits
    # whenever it is set externally
    on_set = await state_register_set_event(args.to_state, state)

    # whenever to_state is set, set from_state. the owner of from_state
    # may then update it, which propagates to to_state, closing the loop
    await set_value(args.from_state, on_set)

    while True:
        await asyncio.sleep(1)


def parse_args():
    import argparse

    p = argparse.ArgumentParser(
        description="""
            make a state which reflects the value of another, and propagates
            sets"""
    )

    p.add_argument("from_state", help="state to observe")
    p.add_argument("to_state", help="state to publish")

    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
