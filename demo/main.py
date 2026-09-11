"""Run this file in PyCharm to read and watch macOS Now Playing metadata."""

import argparse
import asyncio
from datetime import datetime
import sys

from macos_mediaremote import MediaRemote, MediaRemoteError, NowPlaying


WATCH_SECONDS = 60


def format_time(seconds: float | None) -> str:
    if seconds is None:
        return "Unknown"
    sign = "-" if seconds < 0 else ""
    minutes, seconds = divmod(int(abs(seconds)), 60)
    return f"{sign}{minutes}:{seconds:02d}"


def show_state(state: NowPlaying | None, source: str) -> None:
    print(f"\n[{datetime.now():%H:%M:%S}] {source}", flush=True)
    if state is None:
        print("No media session reported. Waiting for player updates.", flush=True)
        return

    status = "Unknown"
    if state.playing is True:
        status = "Playing"
    elif state.playing is False:
        status = "Paused"

    print(f"  Title:    {state.title or 'Unknown'}")
    print(f"  Artist:   {state.artist or 'Unknown'}")
    print(f"  Album:    {state.album or 'Unknown'}")
    print(f"  Player:   {state.bundle_identifier or 'Unknown'}")
    print(f"  Status:   {status}")
    print(f"  Position: {format_time(state.elapsed_time)} / {format_time(state.duration)}")
    print("  Position is from this snapshot; it is not a live timer.", flush=True)


async def main(seconds: int) -> None:
    print("macOS MediaRemote demo", flush=True)
    print(f"Python: {sys.executable}")
    print("Start playback in a media app to see its Now Playing information.")
    print(f"Watching for {seconds} seconds. Ctrl+C also stops the demo.", flush=True)

    remote = MediaRemote()
    show_state(await remote.get(), "Current state")

    async with remote.stream() as events:
        # The deadline cancels iteration; leaving the context closes the helper.
        try:
            async with asyncio.timeout(seconds):
                async for state in events:
                    show_state(state, "Player update")
            print("The player update stream ended.", flush=True)
        except TimeoutError:
            print("\nWatch duration reached.", flush=True)

    print("Demo finished. The subscription is closed.", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=WATCH_SECONDS,
                        help="How long to watch for updates (default: 60 seconds)")
    args = parser.parse_args()
    if args.seconds <= 0:
        parser.error("--seconds must be positive")
    try:
        asyncio.run(main(args.seconds))
    except KeyboardInterrupt:
        print("\nDemo stopped.")
    except MediaRemoteError as exc:
        print(f"\nMediaRemote failed: {exc}", file=sys.stderr)
        if getattr(exc, "stderr", ""):
            print(exc.stderr, file=sys.stderr)
        sys.exit(1)
