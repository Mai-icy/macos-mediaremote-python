"""Read-only example; safe to run without changing playback."""
import asyncio

from macos_mediaremote import MediaRemote


async def main():
    state = await MediaRemote().get()
    if state is None:
        print("No current Now Playing session")
    else:
        print(state.title, "—", state.artist)
        print("Player:", state.bundle_identifier, "Playing:", state.playing)
        print("Position:", state.elapsed_time, "Duration:", state.duration, "seconds")


if __name__ == "__main__":
    asyncio.run(main())
