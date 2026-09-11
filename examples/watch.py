"""Read-only stream; Ctrl-C closes the helper."""
import asyncio

from macos_mediaremote import MediaRemote


async def main():
    async with MediaRemote().stream() as events:
        async for state in events:
            print("No session" if state is None else (state.bundle_identifier, state.title, state.playing))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
