"""Read-only installed-wheel audit. Run from outside the source directory.

Does not send controls or run the upstream synthetic-media test command.
Prints field availability, never track titles, artwork, or other metadata values.
"""
import argparse
import asyncio
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys

import macos_mediaremote
from macos_mediaremote import MediaRemote


def run(*args):
    return subprocess.check_output(list(map(str, args)), text=True).strip()


async def main(*, resources_only=False, read_once=False):
    package = Path(macos_mediaremote.__file__).resolve().parent
    assert Path(sys.prefix).resolve() in package.parents, "Must import from installed virtualenv"
    root = package / "_native"
    framework = root / "MediaRemoteAdapter.framework"
    binary = framework / "MediaRemoteAdapter"
    assert not any(p.is_symlink() for p in root.rglob("*"))
    lock = json.loads((root / "upstream.lock.json").read_text())
    assert lock["package_version"] == macos_mediaremote.__version__
    metadata = importlib.metadata.distribution("macos-mediaremote-python")
    assert metadata.version == lock["package_version"]
    wheel = metadata.read_text("WHEEL")
    assert "Root-Is-Purelib: false" in wheel
    expected_tag = "macosx_" + lock["deployment_target"].replace(".", "_") + "_universal2"
    assert "Tag: py3-none-" + expected_tag in wheel
    assert not metadata.requires
    archs = run("lipo", "-archs", binary).split()
    assert sorted(archs) == ["arm64", "x86_64"]
    run("codesign", "--verify", "--strict", "--all-architectures", framework)
    assert (root / "mediaremote-adapter.pl").is_file()
    assert "Jonas van den Berg" in (root / "LICENSE.upstream").read_text()
    libraries = run("otool", "-L", binary)
    dependencies = [line.strip().split(" (", 1)[0] for line in libraries.splitlines()
                    if line.startswith("\t")]
    assert dependencies and all(
        path == "@rpath/MediaRemoteAdapter.framework/MediaRemoteAdapter"
        or path.startswith(("/System/Library/", "/usr/lib/")) for path in dependencies
    ), libraries
    versions = run("vtool", "-show-build", binary)
    targets = re.findall(r"^\s*minos\s+(\S+)", versions, re.MULTILINE)
    assert targets == [lock["deployment_target"]] * len(archs), versions
    print("Installed:", package)
    print("Architectures:", archs, "Signature: valid, ad-hoc")
    print("Linked libraries:\n" + libraries)
    print("Build versions:\n" + versions)
    if resources_only:
        return
    client = MediaRemote(initialization_timeout=5)
    state = await client.get()
    print("get:", "empty session" if state is None else "nonempty snapshot")
    if state is not None:
        print("Available fields:", sorted(state.raw))
    if read_once:
        return
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
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resources-only", action="store_true", help="Check packaging without native calls")
    mode.add_argument("--read-once", action="store_true", help="Also run get, without starting a stream")
    args = parser.parse_args()
    asyncio.run(main(resources_only=args.resources_only, read_once=args.read_once))
