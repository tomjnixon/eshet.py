import eshet
import asyncio


async def main(args):
    client = eshet.Client()

    async def set_cb(new_value):
        return await client.set(args.from_state, new_value)

    state = await client.state_register(args.to_state, set_cb)

    initial_value = await client.state_observe(args.from_state, state.changed)
    await state.changed(initial_value)

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
