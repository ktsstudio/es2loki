import asyncio
import logging
import os
import signal
import time
from typing import Any, Dict, Optional

__all__ = ("Command", "run_command")


class ExceptionExit(SystemExit):
    code = 1


class TimeoutExit(SystemExit):
    code = 2


class ForceExit(SystemExit):
    code = 3


class Command:
    def __init__(
        self,
        *,
        execute_timeout: float = 30,
        cleanup_timeout: float = 60,
        command_kwargs: Optional[Dict[str, Any]] = None
    ):
        super().__init__()

        self._loop = None
        self._logger = logging.getLogger("{}".format(self.__class__.__name__))

        self._execute_timeout = execute_timeout
        self._cleanup_timeout = cleanup_timeout
        self._stop_event = asyncio.Event()

        self._command_kwargs = command_kwargs or {}

        self.post_init()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def post_init(self):
        pass

    @property
    def execute_timeout(self):
        return self._execute_timeout

    @property
    def cleanup_timeout(self):
        return self._cleanup_timeout

    @property
    def is_running(self) -> bool:
        return not self._stop_event.is_set()

    @property
    def stop_event(self) -> asyncio.Event:
        return self._stop_event

    def get_command_kwarg(self, name: str) -> Optional[Any]:
        return self._command_kwargs.get(name)

    def start(self, *args, **kwargs) -> int:
        if os.name == "nt":
            return self.start_win(*args, **kwargs)

        for s in (signal.SIGINT, signal.SIGTERM):
            self.loop.add_signal_handler(s, self._on_exit, s)

        return self.loop.run_until_complete(self.start_async(*args, **kwargs))

    def start_win(self, *args, **kwargs) -> int:
        # this requires
        # `cli(standalone_mode=False)`
        # in manage.py
        # so that click won't silently swallow KeyboardInterrupt

        try:
            return self.loop.run_until_complete(self.start_async(*args, **kwargs))
        except KeyboardInterrupt:
            self._on_exit(signal.SIGINT)
            return 0

    async def start_async(self, *args, **kwargs) -> int:
        time_start = time.time()
        try:
            self.logger.info("Starting %s...", self.__class__.__name__)

            execute_dt = await self._start_async(*args, **kwargs)

            time_end = time.time()

            self.logger.info(
                "Finished %s with exit code 0. " "elapsed: %.3fs " "execute: %.3fs ",
                self.__class__.__name__,
                time_end - time_start,
                execute_dt,
            )
            return 0
        except KeyboardInterrupt:
            pass
        except SystemExit as e:
            time_end = time.time()
            self.logger.info(
                "Finished %s with exit code %d (%s). elapsed %.3fs",
                self.__class__.__name__,
                e.code,
                e.__class__.__name__,
                time_end - time_start,
            )
            return e.code

        return 0

    # pylint: disable=too-many-branches,too-many-statements
    async def _start_async(self, *args, **kwargs) -> float:
        time_exec_start = time.time()
        time_exec_end = 0.0

        if self.is_running:
            self._execute_task = self.loop.create_task(self.execute(*args, **kwargs))

            fs = [self._execute_task, self._stop_event.wait()]
            await asyncio.wait(fs, return_when=asyncio.FIRST_COMPLETED)

        if self._execute_task and self._execute_task.done():
            if not self._execute_task.cancelled():
                exc = self._execute_task.exception()
                if not exc:
                    self.logger.info("execute has finished successfully")
                else:
                    self.logger.exception(
                        "execute has finished with an exception: %s", exc, exc_info=exc
                    )
                    raise ExceptionExit() from exc
            time_exec_end = time.time()
            self._stop_event.set()

        if (
            self._execute_task
            and not self._execute_task.cancelled()
            and not self._execute_task.done()
        ):

            self.logger.debug(
                "Waiting for execute to finish within %.2fs...", self.execute_timeout
            )
            try:
                await asyncio.wait_for(self._execute_task, timeout=self.execute_timeout)
            except asyncio.TimeoutError as e:
                self.logger.error(
                    "execute has not finished within %.2fs", self.execute_timeout
                )
                raise TimeoutExit() from e
            except Exception as e:
                self.logger.exception("execute has finished with an exception: %s", e)
                raise ExceptionExit() from e
            finally:
                time_exec_end = time.time()

        if time_exec_end == 0:
            time_exec_end = time.time()

        return time_exec_end - time_exec_start

    def _on_exit(self, sig):
        if self._stop_event.is_set():
            raise ForceExit()

        self.logger.info(
            "Got %s signal - exiting",
            signal.Signals(sig).name,  # pylint: disable=no-member
        )
        self._stop_event.set()

    async def execute(self, *args, **kwargs):
        pass
