"""Read-only installed-wheel audit. Run from outside the source directory.

Does not send controls or run the upstream synthetic-media test command.
Prints field availability, never track titles, artwork, or other metadata values.
"""
import asyncio
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

import macos_mediaremote
from macos_mediaremote import MediaRemote


def run(*args):
    return subprocess.check_output(list(map(str, args)), text=True).strip()


async def main():
    package = Path(macos_mediaremote.__file__).resolve().parent
    assert Path(sys.prefix).resolve() in package.parents, "Must import from installed virtualenv"
    root = package / "_native"
    framework = root / "MediaRemoteAdapter.framework"
    binary = framework / "MediaRemoteAdapter"
    assert not any(p.is_symlink() for p in root.rglob("*"))
    lock = json.loads((root / "upstream.lock.json").read_text())
    assert lock["package_version"] == macos_mediaremote.__version__
    metadata = importlib.metadata.distribution("macos-mediaremote-python")
    wheel = metadata.read_text("WHEEL")
    assert "Root-Is-Purelib: false" in wheel
    assert "Tag: py3-none-macosx_11_0_universal2" in wheel
    assert not metadata.requires
    archs = run("lipo", "-archs", binary).split()
    assert sorted(archs) == ["arm64", "x86_64"]
    run("codesign", "--verify", "--strict", "--all-architectures", framework)
    print("Installed:", package)
    print("Architectures:", archs, "Signature: valid, ad-hoc")
    print("Linked libraries:\n" + run("otool", "-L", binary))
    print("Build versions:\n" + run("vtool", "-show-build", binary))
    client = MediaRemote(initialization_timeout=5)
    state = await client.get()
    print("get:", "empty session" if state is None else "nonempty snapshot")
    if state is not None:
        print("Available fields:", sorted(state.raw))
    async with client.stream() as events:
        first = await anext(events)
        print("stream initial:", "empty session" if first is None else "nonempty snapshot")
        # Private attributes are used only for this implementation audit.
        process = events._process.proc
        count = 0

        async def consume():
            nonlocal count
            async for _ in events:
                count += 1

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(6)
        assert process.returncode is None, "Helper unexpectedly exited"
        assert not consumer.done(), "Subscription unexpectedly finished"
        consumer.cancel()
        try:
            await consumer
        except asyncio.CancelledError:
            pass
    assert process.returncode is not None
    print("stream: 6 seconds open, additional events:", count, "helper reaped:", process.returncode)
    print("stderr retained bytes:", len(events.stderr.encode("utf-8")))


if __name__ == "__main__":
    asyncio.run(main())
