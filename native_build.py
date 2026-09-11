"""Build only at wheel creation; never imported by the installed package."""
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(*args):
    subprocess.run(list(map(str, args)), check=True)


def build_native(destination: Path):
    if sys.platform != "darwin":
        raise RuntimeError("Native wheels must be built on macOS with Xcode CLT and CMake")
    lock = json.loads((ROOT / "upstream.lock.json").read_text())
    cache = ROOT / ".build" / "upstream" / "source.tar.gz"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        with urllib.request.urlopen(lock["archive_url"], timeout=60) as response:
            data = response.read(16 * 1024 * 1024 + 1)
        if hashlib.sha256(data).hexdigest() != lock["archive_sha256"]:
            raise RuntimeError("Upstream archive SHA-256 mismatch")
        cache.write_bytes(data)
    if hashlib.sha256(cache.read_bytes()).hexdigest() != lock["archive_sha256"]:
        raise RuntimeError("Cached upstream archive SHA-256 mismatch; remove it and retry")
    # Always extract verified bytes into a fresh tree; never trust an edited checkout.
    with tempfile.TemporaryDirectory(prefix="native-", dir=ROOT / ".build") as temp:
        work = Path(temp)
        with tarfile.open(cache) as archive:
            for member in archive.getmembers():
                if (member.name.startswith("/") or ".." in Path(member.name).parts
                        or not (member.isfile() or member.isdir())):
                    raise RuntimeError("Unexpected archive member")
            archive.extractall(work, filter="data")
        source = work / ("mediaremote-adapter-" + lock["commit"])
        build = work / "build"
        run("cmake", "-S", source, "-B", build, "-DCMAKE_BUILD_TYPE=Release",
            "-DCMAKE_OSX_DEPLOYMENT_TARGET=" + lock["deployment_target"])
        run("cmake", "--build", build, "--target", "MediaRemoteAdapter", "--parallel", "4")
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        # A flat framework avoids relying on wheel installers preserving symlinks.
        framework = destination / "MediaRemoteAdapter.framework"
        shutil.copytree(build / "MediaRemoteAdapter.framework" / "Versions" / "A",
                        framework, ignore=shutil.ignore_patterns("_CodeSignature"))
        binary = framework / "MediaRemoteAdapter"
        run("install_name_tool", "-id", "@rpath/MediaRemoteAdapter.framework/MediaRemoteAdapter", binary)
        run("codesign", "--force", "--sign", "-", framework)
        run("codesign", "--verify", "--strict", "--all-architectures", framework)
        archs = subprocess.check_output(["lipo", "-archs", str(binary)], text=True).split()
        if sorted(archs) != sorted(lock["architectures"]):
            raise RuntimeError(f"Unexpected architectures: {archs}")
        shutil.copy2(source / "bin" / "mediaremote-adapter.pl", destination)
        shutil.copy2(source / "LICENSE", destination / "LICENSE.upstream")
        shutil.copy2(ROOT / "upstream.lock.json", destination)
        if (source / "LICENSE").read_bytes() != (ROOT / "licenses" / "mediaremote-adapter.txt").read_bytes():
            raise RuntimeError("Bundled upstream license differs from verified source")
