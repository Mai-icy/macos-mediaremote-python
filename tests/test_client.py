import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from macos_mediaremote import (
    Command, HelperError, HelperTimeoutError, MediaRemote, ProtocolError, UnsupportedPlatformError,
)
from macos_mediaremote._process import Process, STDERR_LIMIT

EVENT = json.dumps({"type": "data", "diff": False, "payload": {"title": "音乐🎵"}}, ensure_ascii=False) + "\n"
EMIT = f"os.write(1, {EVENT.encode()!r})\n"


async def test_get_pretty_json_and_options(helpers):
    make, _ = helpers
    client = make('assert sys.argv[1:] == ["get", "--micros", "--allow-missing-title", "--no-artwork"]\n'
                  'print(json.dumps({"title": "example", "durationMicros": 3000000}, indent=2))\n')
    assert (await client.get()).duration == 3


async def test_fragmented_utf8_multiline_and_normal_exit(helpers):
    make, _ = helpers
    code = f"data = {EVENT.encode()!r}\nfor byte in data:\n os.write(1, bytes([byte])); time.sleep(0.001)\n"
    code += 'os.write(1, b\'{"type":"data","diff":false,"payload":{}}\\n\')\n'
    async with make(code).stream() as stream:
        assert (await anext(stream)).title == "音乐🎵"
        assert await anext(stream) is None
        with pytest.raises(StopAsyncIteration):
            await anext(stream)


async def test_idle_longer_than_initial_timeout_and_cancel(helpers):
    make, processes = helpers
    async with make(EMIT + "time.sleep(30)\n", initialization_timeout=2.0).stream() as stream:
        await anext(stream)
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(2.2)
        assert not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert processes[0].proc.returncode is not None


async def test_stderr_flood_is_consumed_and_bounded(helpers):
    make, _ = helpers
    code = 'os.write(2, b"x" * 200000 + b"diagnostic-tail")\n' + EMIT + 'time.sleep(30)\n'
    async with make(code).stream() as stream:
        assert (await anext(stream)).title
        assert stream.stderr.endswith("diagnostic-tail")
        assert len(stream.stderr) == STDERR_LIMIT


async def test_early_break_context_body_exception_and_idempotent_close(helpers):
    make, _ = helpers
    client = make(EMIT + "time.sleep(30)\n")
    async with client.stream() as stream:
        async for _ in stream:
            break
    await stream.aclose()
    with pytest.raises(RuntimeError, match="consumer"):
        async with client.stream():
            raise RuntimeError("consumer")


async def test_nonzero_exit_retains_stderr(helpers):
    make, _ = helpers
    client = make('os.write(2, b"cannot load framework"); sys.exit(7)\n')
    with pytest.raises(HelperError) as caught:
        await client.get()
    assert caught.value.returncode == 7
    assert caught.value.stderr == "cannot load framework"
    with pytest.raises(HelperError):
        async with client.stream():
            pass


async def test_stream_exit_after_event(helpers):
    make, _ = helpers
    async with make(EMIT + 'os.write(2, b"failed"); sys.exit(9)\n').stream() as stream:
        await anext(stream)
        with pytest.raises(HelperError) as caught:
            await anext(stream)
        assert caught.value.returncode == 9 and caught.value.stderr == "failed"


@pytest.mark.parametrize("code", ['print("not json")\n', 'os.write(1, b"\\xff\\n")\n',
                                     'os.write(1, b"{}"); sys.exit(0)\n', 'sys.exit(0)\n'])
async def test_bad_stream_cleans_up(helpers, code):
    make, _ = helpers
    with pytest.raises(ProtocolError):
        async with make(code).stream():
            pass


@pytest.mark.parametrize("mode", ["get", "stream"])
async def test_oversized_stdout(helpers, mode):
    make, _ = helpers
    client = make('os.write(1, b"x" * 5000); time.sleep(30)\n', max_output_bytes=1024)
    with pytest.raises(ProtocolError):
        if mode == "get":
            await client.get()
        else:
            async with client.stream():
                pass


async def test_initial_timeout_and_command_timeout(helpers):
    make, _ = helpers
    client = make('time.sleep(30)\n', timeout=0.2, initialization_timeout=0.2)
    with pytest.raises(HelperTimeoutError) as caught:
        await client.get()
    assert caught.value.stderr == ""
    with pytest.raises(HelperTimeoutError):
        async with client.stream():
            pass


async def test_timeout_retains_received_stderr(helpers, monkeypatch):
    make, _ = helpers
    original = Process.read_all

    async def expire_after_diagnostic(self):
        # Start the short deadline after output arrives, not during interpreter startup.
        while self.stderr != "waiting":
            await asyncio.sleep(0.01)
        async with asyncio.timeout(0.02):
            return await original(self)

    monkeypatch.setattr(Process, "read_all", expire_after_diagnostic)
    client = make('os.write(2, b"waiting"); time.sleep(30)\n')
    with pytest.raises(HelperTimeoutError) as caught:
        await client.get()
    assert caught.value.stderr == "waiting"


async def test_cancellation_during_get(helpers):
    make, processes = helpers
    task = asyncio.create_task(make("time.sleep(30)\n").get())
    while not processes:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_ignores_term_and_repeated_cancellation(helpers):
    make, processes = helpers
    async with make('signal.signal(signal.SIGTERM, signal.SIG_IGN)\n' + EMIT + 'time.sleep(30)\n').stream() as stream:
        await anext(stream)
        task = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        assert processes[0].proc.returncode == -9


async def test_slow_consumer_backpressure_close(helpers):
    make, _ = helpers
    code = EMIT + f"while True: os.write(1, {EVENT.encode()!r})\n"
    async with make(code, max_output_bytes=1024).stream() as stream:
        await anext(stream)
        await asyncio.sleep(0.05)


@pytest.mark.parametrize("method,expected", [("play", 0), ("pause", 1), ("toggle_play_pause", 2),
                                          ("next_track", 4), ("previous_track", 5)])
async def test_control_mapping(helpers, method, expected):
    make, _ = helpers
    client = make(f"assert sys.argv[1:] == ['send', '{expected}']\n")
    await getattr(client, method)()


@pytest.mark.parametrize("value,expected", [(0, "0"), (1.234567, "1234567"), (0.0000009, "1")])
async def test_seek_units(helpers, value, expected):
    make, _ = helpers
    await make(f"assert sys.argv[1:] == ['seek', '{expected}']\n").seek(value)


@pytest.mark.parametrize("value", [-1, -0.00000001, "3; touch file", True, None, float("inf"), float("nan"), 10**1000])
async def test_seek_invalid_before_spawn(value):
    with pytest.raises(ValueError):
        await MediaRemote().seek(value)


@pytest.mark.parametrize("method", ["play", "seek"])
async def test_controls_fail_and_timeout(helpers, method):
    make, _ = helpers
    args = [1] if method == "seek" else []
    with pytest.raises(HelperError):
        await getattr(make('sys.exit(2)\n'), method)(*args)
    with pytest.raises(HelperTimeoutError):
        await getattr(make('time.sleep(30)\n', timeout=0.2), method)(*args)


async def test_current_player_is_not_locked(helpers):
    make, _ = helpers
    # A snapshot of A provides no target token to the subsequent global control.
    code = 'if sys.argv[1] == "get": print(\'{"bundleIdentifier":"player.A"}\')\n'
    code += 'else: assert sys.argv[1:] == ["send", "0"]\n'
    client = make(code)
    assert (await client.get()).bundle_identifier == "player.A"
    await client.play()


async def test_inherited_upstream_options_are_removed(helpers, monkeypatch):
    make, _ = helpers
    monkeypatch.setenv("MEDIAREMOTEADAPTER_OPTION_human_readable", "")
    client = make('assert not any(k.startswith("MEDIAREMOTEADAPTER_") for k in os.environ)\nprint("null")\n')
    assert await client.get() is None


async def test_artwork_option_and_invalid_command(monkeypatch):
    client = MediaRemote(include_artwork=True)
    runner = AsyncMock(return_value=b"null\n")
    monkeypatch.setattr(client, "_run", runner)
    await client.get()
    assert "--no-artwork" not in runner.call_args.args
    with pytest.raises(ValueError):
        await client.send(0)
    await client.send(Command.PLAY)


@pytest.mark.parametrize("kwargs", [{"timeout": 0}, {"initialization_timeout": float("nan")},
                                    {"max_output_bytes": True}, {"include_artwork": 1}])
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        MediaRemote(**kwargs)


async def test_unsupported_platform(monkeypatch):
    monkeypatch.setattr("macos_mediaremote.client.sys.platform", "linux")
    with pytest.raises(UnsupportedPlatformError):
        await MediaRemote().get()


async def test_spawn_failure(monkeypatch):
    client = MediaRemote()
    monkeypatch.setattr(client, "_argv", lambda *args: ["/nonexistent/mediaremote-helper"])
    with pytest.raises(HelperError):
        await client.get()


async def test_cancel_during_process_creation(helpers, monkeypatch):
    make, processes = helpers
    original = asyncio.create_subprocess_exec
    created = asyncio.Event()

    async def delayed(*args, **kwargs):
        process = await original(*args, **kwargs)
        created.set()
        await asyncio.sleep(0.1)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed)
    task = asyncio.create_task(make("time.sleep(30)\n").get())
    await created.wait()
    task.cancel()
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processes[0].proc.returncode is not None


async def test_malformed_event_after_initial_snapshot(helpers):
    make, _ = helpers
    async with make(EMIT + 'print("malformed"); time.sleep(30)\n').stream() as stream:
        await anext(stream)
        with pytest.raises(ProtocolError):
            await anext(stream)


async def test_initialization_timeout_does_not_cover_consumer(helpers):
    make, _ = helpers
    async with make(EMIT + "time.sleep(30)\n", initialization_timeout=2.0).stream() as stream:
        await asyncio.sleep(2.2)
        assert (await anext(stream)).title == "音乐🎵"
