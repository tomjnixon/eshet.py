Examples in this directory should have argument parsers which describe how they
are used -- run them with `--help`.

eshet.py uses the same `ESHET_SERVER` environment variable [as
eshetcpp](https://github.com/tomjnixon/eshetcpp#cli-usage) to find the server
by default. You may need to set it to run the examples.

## bind_state.py

Make a state which reflects the value of another, and propagates sets,
implemented with the normal API.

For example, running these commands:

    python examples/bind_state.py /a /b
    eshet publish /a
    eshet observe /a

values typed into `publish` will appear from `observe`

## bind_state_yarp.py

The same (or very nearly) as `bind_state.py`, but implemented using the yarp
wrappers.

## event_to_state_timer.py

Something like a typical PIR light controller. Listens to an event, and
publishes a state which is true if any events were emitted recently.

For example, run these commands:

    python examples/event_to_state_timer.py /event /state
    eshet observe /state

Then run this to see the output of `observe` change from false to true:

    eshet emit /event null
