"""Async API over the upstream get, stream, send and seek commands."""
import asyncio
from contextlib import asynccontextmanager
from enum import IntEnum
import math
from pathlib import Path
import sys
from typing import AsyncIterator

from ._process import Process
from .errors import HelperError, HelperTimeoutError, ProtocolError, UnsupportedPlatformError
from .models import NowPlaying, decode_json, parse_event, parse_snapshot


class Command(IntEnum):
    PLAY = 0
    PAUSE = 1
    TOGGLE_PLAY_PAUSE = 2
    NEXT_TRACK = 4
    PREVIOUS_TRACK = 5


def positive_seconds(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be positive finite seconds")
    try:
        valid = math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be positive finite seconds")


class EventStream:
    """Iterator owned by MediaRemote.stream()'s async context manager."""

    def __init__(self, process):
        self._process = process
        self._closed = False
        self._pending = []

    @property
    def stderr(self) -> str:
        """Most recent 64 KiB of diagnostics; nonfatal stderr does not stop iteration."""
        return self._process.stderr

    def __aiter__(self):
        return self

    async def __anext__(self) -> NowPlaying | None:
        if self._closed:
            raise StopAsyncIteration
        if self._pending:
            return self._pending.pop()
        try:
            line = await self._process.readline()
            if not line:
                await self._process.check_exit()
                raise StopAsyncIteration
            return parse_event(line)
        except BaseException:
            await self.aclose()
            raise

    async def aclose(self):
        """Idempotent; call after iteration stops, not concurrently with __anext__."""
        self._closed = True
        await self._process.close()


class MediaRemote:
    """System Now Playing client; construction/import starts no process."""

    def __init__(self, *, timeout: float = 5.0, initialization_timeout: float = 5.0,
                 include_artwork: bool = False, max_output_bytes: int = 4 * 1024 * 1024):
        positive_seconds(timeout, "timeout")
        positive_seconds(initialization_timeout, "initialization_timeout")
        if type(max_output_bytes) is not int or not 1024 <= max_output_bytes <= 64 * 1024 * 1024:
            raise ValueError("max_output_bytes must be an integer between 1024 and 67108864")
        if not isinstance(include_artwork, bool):
            raise ValueError("include_artwork must be boolean")
        self.timeout = timeout
        self.initialization_timeout = initialization_timeout
        self.include_artwork = include_artwork
        self.max_output_bytes = max_output_bytes

    def _argv(self, *args):
        if sys.platform != "darwin":
            raise UnsupportedPlatformError("MediaRemote requires macOS")
        root = Path(__file__).resolve().parent / "_native"
        script = root / "mediaremote-adapter.pl"
        framework = root / "MediaRemoteAdapter.framework"
        if not script.is_file() or not (framework / "MediaRemoteAdapter").is_file():
            raise HelperError("Bundled helper missing; build and install the macOS wheel")
        return ["/usr/bin/perl", str(script), str(framework), *args]

    def _options(self):
        options = ["--micros", "--allow-missing-title"]
        if not self.include_artwork:
            options.append("--no-artwork")
        return options

    async def _run(self, *args):
        process = Process(self._argv(*args), self.max_output_bytes)
        try:
            async with asyncio.timeout(self.timeout):
                await process.start()
                output = await process.read_all()
                await process.check_exit()
                return output
        except TimeoutError as exc:
            raise HelperTimeoutError("Helper command timed out", stderr=process.stderr) from exc
        finally:
            await process.close()

    async def get(self) -> NowPlaying | None:
        """Read one snapshot. None means upstream reports no current session."""
        return parse_snapshot(decode_json(await self._run("get", *self._options())))

    @asynccontextmanager
    async def stream(self) -> AsyncIterator[EventStream]:
        """Start a persistent stream; use `async with client.stream() as events`.

        Enter waits for a first valid snapshot, which is retained for iteration.
        Subsequent silence has no timeout. Context exit terminates/reaps the helper.
        The initial snapshot is not an upstream subscription-ready barrier.
        """
        process = Process(self._argv("stream", "--no-diff", *self._options()), self.max_output_bytes)
        events = EventStream(process)
        try:
            try:
                async with asyncio.timeout(self.initialization_timeout):
                    await process.start()
                    first = await anext(events)
                    events._pending.append(first)
            except TimeoutError as exc:
                raise HelperTimeoutError("Initial snapshot timed out", stderr=process.stderr) from exc
            except StopAsyncIteration as exc:
                raise ProtocolError("Stream exited before its initial snapshot") from exc
            yield events
        finally:
            await events.aclose()

    async def send(self, command: Command) -> None:
        """Dispatch to the current player; success is not an application acknowledgement."""
        if not isinstance(command, Command):
            raise ValueError("command must be a Command member")
        await self._run("send", str(int(command)))

    async def play(self) -> None:
        await self.send(Command.PLAY)

    async def pause(self) -> None:
        await self.send(Command.PAUSE)

    async def toggle_play_pause(self) -> None:
        await self.send(Command.TOGGLE_PLAY_PAUSE)

    async def next_track(self) -> None:
        await self.send(Command.NEXT_TRACK)

    async def previous_track(self) -> None:
        await self.send(Command.PREVIOUS_TRACK)

    async def seek(self, position: float) -> None:
        """Seek to nonnegative seconds, rounded to nearest integer microsecond."""
        if isinstance(position, bool) or not isinstance(position, (int, float)):
            raise ValueError("position must be finite nonnegative seconds")
        try:
            micros = round(position * 1_000_000)
        except (OverflowError, ValueError) as exc:
            raise ValueError("position must be finite nonnegative seconds") from exc
        if position < 0 or not 0 <= micros <= 2**63 - 1:
            raise ValueError("position exceeds the upstream signed 64-bit microsecond range")
        await self._run("seek", str(micros))
