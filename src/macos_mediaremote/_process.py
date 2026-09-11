"""Bounded subprocess transport. No shell, polling, or automatic restarts."""
import asyncio
import os

from .errors import HelperError, ProtocolError

STDERR_LIMIT = 64 * 1024


async def complete_cleanup(task):
    """Finish cleanup even when a caller cancels more than once."""
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    return result


class Process:
    def __init__(self, argv, limit):
        self.argv = argv
        self.limit = limit
        self.proc = None
        self.stderr_task = None
        self.close_task = None
        self.tail = bytearray()

    @property
    def stderr(self):
        return bytes(self.tail).decode("utf-8", errors="replace")

    async def start(self):
        # Do not let inherited upstream option env vars override our protocol.
        env = {k: v for k, v in os.environ.items() if not k.startswith("MEDIAREMOTEADAPTER_")}
        task = asyncio.create_task(asyncio.create_subprocess_exec(
            *self.argv, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            limit=self.limit, env=env,
        ))
        try:
            self.proc = await asyncio.shield(task)
        except asyncio.CancelledError:
            async def recover():
                try:
                    self.proc = await task
                except OSError:
                    return
                self.stderr_task = asyncio.create_task(self._stderr())
                await self.close()
            await complete_cleanup(asyncio.create_task(recover()))
            raise
        except OSError as exc:
            raise HelperError(f"Cannot start helper: {exc}") from exc
        self.stderr_task = asyncio.create_task(self._stderr())

    async def _stderr(self):
        while chunk := await self.proc.stderr.read(8192):
            self.tail.extend(chunk)
            del self.tail[:-STDERR_LIMIT]

    async def read_all(self):
        result = bytearray()
        while chunk := await self.proc.stdout.read(8192):
            result.extend(chunk)
            if len(result) > self.limit:
                raise ProtocolError("Helper stdout exceeds max_output_bytes")
        return bytes(result)

    async def readline(self):
        try:
            line = await self.proc.stdout.readline()
        except ValueError as exc:
            raise ProtocolError("Event exceeds max_output_bytes") from exc
        if len(line) > self.limit:
            raise ProtocolError("Event exceeds max_output_bytes")
        if line and not line.endswith(b"\n"):
            raise ProtocolError("Truncated event: missing final newline")
        return line

    async def check_exit(self):
        code = await self.proc.wait()
        await self.stderr_task
        if code:
            raise HelperError(f"Helper exited with status {code}", returncode=code, stderr=self.stderr)

    async def _close(self):
        if self.proc is None:
            return
        if self.proc.returncode is None:
            try:
                self.proc.terminate()
            except ProcessLookupError:
                pass
        # Drain remaining stdout, including when a slow consumer stopped reading.
        async def drain():
            while await self.proc.stdout.read(8192):
                pass
        drain_task = asyncio.create_task(drain())
        try:
            await asyncio.wait_for(self.proc.wait(), 1.0)
        except TimeoutError:
            try:
                self.proc.kill()
            except ProcessLookupError:
                pass
            await self.proc.wait()
        finally:
            await asyncio.gather(drain_task, self.stderr_task)

    async def close(self):
        if self.close_task is None:
            self.close_task = asyncio.create_task(self._close())
        await complete_cleanup(self.close_task)
