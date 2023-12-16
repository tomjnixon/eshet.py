API
===

ESHET Client
------------

.. py:module:: eshet

.. autoclass:: eshet.Client
.. py:data:: eshet.Unknown

   value used for states when they are not known
.. autoclass:: eshet.TimeoutConfig

YARP Wrapper
------------

.. py:module:: eshet.yarp

YARP wrappers for ESHET use a default shared client if `client` is not specified; see :func:`get_default_eshet_client` and :func:`set_default_eshet_client`.

.. autofunction:: action_call
.. autofunction:: set_value

Events
~~~~~~

.. autofunction:: event_listen

States
~~~~~~

.. autofunction:: state_observe
.. autofunction:: state_register
.. autofunction:: state_register_set_event

Default Client
~~~~~~~~~~~~~~
.. autofunction:: get_default_eshet_client
.. autofunction:: set_default_eshet_client

Utilities
---------

.. py:module:: eshet.utils
.. autofunction:: in_task
.. autoclass:: TaskStrategy
.. autoclass:: RunSerially
