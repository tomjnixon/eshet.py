# eshet.py

A python and asyncio client for ESHET, compatible with
[eshetsrv](https://github.com/tomjnixon/eshetsrv).

Have a look at [the examples](examples) to see how it works.

## install

It's a standard python package, so install it into a virtualenv with `pip install .`

The only quirk is that the `eshet.yarp` module requires use of [my fork of
yarp](https://github.com/tomjnixon/yarp). This is specified in the package, but
might need special attention if you already have some other version installed.
This really needs renaming.

## develop

    pip install -e .[test,dev]

format:

    black eshet examples

lint:
    
    flake8 eshet examples

test:
    
    pytest

For some tests (marked `needs_server`), a running ESHET server is required.

## license

```
Copyright 2023 Thomas Nixon

This program is free software: you can redistribute it and/or modify it under
the terms of version 3 of the GNU General Public License as published by the
Free Software Foundation.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

See LICENSE.
```
