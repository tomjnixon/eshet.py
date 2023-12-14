from eshet.yarp import event_listen, state_register
import yarp
import asyncio


async def main(args):
    event = await event_listen(args.from_event)

    timer = yarp.len(yarp.time_window(event, args.time)) > 0

    await state_register(args.to_state, yarp.no_repeat(timer))

    while True:
        await asyncio.sleep(1)


def parse_args():
    import argparse

    p = argparse.ArgumentParser(
        description="""
            make a state which is true if an event has fired recently, and
            false otherwise"""
    )

    p.add_argument("--time", type=float, help="timer length in seconds", default=3)
    p.add_argument("from_event", help="event to trigger timer")
    p.add_argument("to_state", help="state to publish")

    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
