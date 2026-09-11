import sys

import pytest

from macos_mediaremote import MediaRemote
from macos_mediaremote._process import Process


@pytest.fixture
def helpers(monkeypatch, tmp_path):
    processes = []
    original = Process.start

    async def tracked(self):
        try:
            await original(self)
        finally:
            if self.proc is not None:
                processes.append(self)

    monkeypatch.setattr(Process, "start", tracked)

    def make(code, **options):
        script = tmp_path / f"helper with spaces {len(list(tmp_path.iterdir()))}.py"
        script.write_text("import os, sys, time, json, signal\n" + code)
        client = MediaRemote(**options)
        monkeypatch.setattr(client, "_argv", lambda *args: [sys.executable, "-u", str(script), *args])
        return client

    yield make, processes
    for process in processes:
        assert process.proc.returncode is not None, "Unreaped helper process"
        assert process.stderr_task.done(), "Leaked stderr task"
        assert process.close_task.done(), "Leaked cleanup task"
