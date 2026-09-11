import json
from pathlib import Path
import runpy
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
checks = runpy.run_path(str(ROOT / "release_checks.py"))


@pytest.fixture
def release_tree(tmp_path):
    for name in ["pyproject.toml", "upstream.lock.json", "src/macos_mediaremote/__init__.py"]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    return tmp_path


def test_current_release_configuration():
    project, lock = checks["read_configuration"]()
    assert project["version"] == lock["package_version"]
    assert checks["platform_tag"](lock) == "macosx_11_0_universal2"


@pytest.mark.parametrize("name", ["pyproject.toml", "upstream.lock.json", "src/macos_mediaremote/__init__.py"])
def test_version_drift_fails(release_tree, name):
    path = release_tree / name
    path.write_text(path.read_text().replace("0.1.0a1", "0.1.0a2"))
    with pytest.raises(ValueError, match="versions must match"):
        checks["read_configuration"](release_tree)


@pytest.mark.parametrize("field,value", [
    ("architectures", ["arm64"]), ("deployment_target", "10.15"),
    ("deployment_target", "11"), ("commit", "main"),
    ("archive_sha256", "bad"), ("archive_url", "https://example.org/latest.tar.gz"),
])
def test_invalid_native_configuration_fails(release_tree, field, value):
    path = release_tree / "upstream.lock.json"
    lock = json.loads(path.read_text())
    lock[field] = value
    path.write_text(json.dumps(lock))
    with pytest.raises(ValueError):
        checks["read_configuration"](release_tree)


@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/tags/v0.1.0", "refs/tags/0.1.0a1", ""])
def test_publishing_requires_exact_version_tag(ref):
    with pytest.raises(ValueError, match="Publishing requires tag"):
        checks["check_publish_ref"]("0.1.0a1", ref)


def test_matching_publish_tag():
    checks["check_publish_ref"]("0.1.0a1", "refs/tags/v0.1.0a1")
