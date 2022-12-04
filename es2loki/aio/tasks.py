import asyncio
import functools
from typing import Optional


def _release_waiter(waiter, *args):  # pylint: disable=unused-argument
    if not waiter.done():
        waiter.set_result(None)


async def cancel_and_wait(fut, *, timeout: Optional[float] = None):
    """Cancel the *fut* future or task and wait until it completes."""
    loop = asyncio.get_running_loop()
    waiter = loop.create_future()
    cb = functools.partial(_release_waiter, waiter)
    fut.add_done_callback(cb)

    try:
        fut.cancel()
        # We cannot wait on *fut* directly to make
        # sure _cancel_and_wait itself is reliably cancellable.
        await asyncio.wait_for(waiter, timeout=timeout)
    finally:
        fut.remove_done_callback(cb)
