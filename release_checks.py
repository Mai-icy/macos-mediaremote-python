"""Validate release metadata without importing or starting the native helper."""
import ast
import json
import os
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parent


def platform_tag(lock):
    if sorted(lock["architectures"]) != ["arm64", "x86_64"]:
        raise ValueError("The current wheel build requires arm64 and x86_64")
    target = lock["deployment_target"]
    if not re.fullmatch(r"[0-9]+\.[0-9]+", target) or int(target.split(".")[0]) < 11:
        raise ValueError("universal2 requires a macOS deployment target of at least 11.0")
    return "macosx_" + target.replace(".", "_") + "_universal2"


def read_configuration(root=ROOT):
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    lock = json.loads((root / "upstream.lock.json").read_text())
    tree = ast.parse((root / "src/macos_mediaremote/__init__.py").read_text())
    versions = [ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)]
    if versions != [project["version"]] or lock["package_version"] != project["version"]:
        raise ValueError("pyproject.toml, __version__, and upstream.lock.json versions must match")
    if project["name"] != "macos-mediaremote-python":
        raise ValueError("Unexpected distribution name")
    if not re.fullmatch(r"[0-9a-f]{40}", lock["commit"]):
        raise ValueError("Upstream must be pinned to a full commit")
    if not re.fullmatch(r"[0-9a-f]{64}", lock["archive_sha256"]):
        raise ValueError("Upstream archive must have a SHA-256 digest")
    if lock["archive_url"] != "https://codeload.github.com/ungive/mediaremote-adapter/tar.gz/" + lock["commit"]:
        raise ValueError("Archive URL does not match the pinned upstream commit")
    platform_tag(lock)
    return project, lock


def check_publish_ref(version, ref):
    if ref != "refs/tags/v" + version:
        raise ValueError(f"Publishing requires tag v{version}, received {ref!r}")


if __name__ == "__main__":
    project, lock = read_configuration()
    if os.environ.get("PUBLISH_REQUESTED", "false").lower() == "true":
        check_publish_ref(project["version"], os.environ.get("GITHUB_REF", ""))
    print(f"Release configuration verified: {project['name']} {project['version']} {platform_tag(lock)}")
