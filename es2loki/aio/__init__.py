import asyncio
import sys
from asyncio import Future
from typing import Coroutine, Optional, Tuple, TypeVar, Union

from .tasks import cancel_and_wait

T = TypeVar("T")


if sys.version_info >= (3, 9):
    future_type = Future[T]
else:
    future_type = Future  # type: ignore


async def wait_task(
    coro_or_future: Union[future_type, Coroutine[None, None, T]],
    *,
    event: asyncio.Event,
    cancel_timeout: Optional[float] = None,
) -> Tuple[Optional[T], bool]:

    data_task = asyncio.ensure_future(coro_or_future)
    event_wait_task = asyncio.ensure_future(event.wait())
    try:
        fs = [data_task, event_wait_task]

        await asyncio.wait(fs, return_when=asyncio.FIRST_COMPLETED)  # type: ignore

        if event.is_set():
            await cancel_and_wait(data_task, timeout=cancel_timeout)

            if data_task.done() and not data_task.cancelled():
                return data_task.result(), True

            return None, True

        data = await data_task
        return data, False

    finally:
        if not event_wait_task.done():
            event_wait_task.cancel()
        if not data_task.done():
            data_task.cancel()
