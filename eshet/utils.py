import asyncio
import functools


def create_task_in_set(s: set, coro):
    """helper to call create_task(coro), save the result in s, and remove it
    when it's done; returns the task
    """
    task = asyncio.create_task(coro)
    s.add(coro)
    task.add_done_callback(s.discard)
    return task


def in_task(f):
    """decorator: return a function which calls f in a task"""
    tasks = set()

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return create_task_in_set(tasks, f(*args, **kwargs))

    return wrapper
