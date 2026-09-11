# macos-mediaremote-python

An **unofficial**, lightweight asyncio wrapper for
[ungive/mediaremote-adapter](https://github.com/ungive/mediaremote-adapter), targeting
macOS's current Now Playing application.

Import it as `macos_mediaremote`. The distribution name is
`macos-mediaremote-python`, and the current version is `0.1.0a1`. No PyPI package
has been published yet.
The API follows the upstream protocol and has no Spotify, Qt, or third-party
Python runtime dependencies.

## Local installation

Requires Python 3.11+. This repository currently provides source code only.
First build a local wheel using the steps in [Building from source](#building-from-source),
then install it:

```sh
python3 -m venv /tmp/mediaremote-demo
/tmp/mediaremote-demo/bin/python -m pip install --no-index --no-deps \
  dist/macos_mediaremote_python-0.1.0a1-py3-none-macosx_11_0_universal2.whl
/tmp/mediaremote-demo/bin/python examples/read_once.py
```

The wheel includes the framework, upstream Perl script, and licenses. Installing,
importing, and running an installed wheel never downloads native code. Wheel users
do not need Git, CMake, Xcode, or Homebrew.

At runtime, the wrapper invokes macOS's `/usr/bin/perl`, preserving the upstream
`DynaLoader` mechanism for loading the framework. Python does not load the private
framework directly.

## Read the current state

```python
import asyncio
from macos_mediaremote import MediaRemote

async def main():
    remote = MediaRemote()
    state = await remote.get()
    if state is not None:
        print(state.title, state.artist, state.playing)
        print(state.bundle_identifier)
        print(state.elapsed_time, state.duration)  # Seconds
        print(state.raw.get("parentApplicationBundleIdentifier"))

asyncio.run(main())
```

Inside an existing asyncio application, use `await remote.get()` directly.
Each `get()` call starts a short-lived helper process. Importing the package and
constructing `MediaRemote()` have no process or network side effects.

## Subscribe to updates

```python
import asyncio
from macos_mediaremote import MediaRemote

async def main():
    async with MediaRemote().stream() as events:
        async for state in events:
            if state is None:
                print("No current media session")
            else:
                print(state.title, state.playing)

asyncio.run(main())
```

Each `stream()` owns one persistent helper process and must be used with
`async with`. Entering the context waits up to `initialization_timeout` seconds
for the first valid snapshot, which is retained for iteration. Subsequent silence
has no idle timeout. Every event is a complete snapshot (`--no-diff` upstream).
There is no additional synchronous, callback, or automatic reconnection API.

Upstream may emit an empty snapshot before the current media state arrives.
The first `None` does not mean initialization has settled.

- Leaving the context after `break`, a consumer exception, or cancellation closes
  the helper. Cleanup sends SIGTERM, escalates to SIGKILL after one second if
  necessary, and reaps the process.
- Cancellation preserves `asyncio.CancelledError`. `await events.aclose()` is
  idempotent. Do not read the same iterator concurrently or call `aclose()` while
  another task is still awaiting `anext()`. Cancel and await that task first.
- Clean EOF before the first snapshot is a protocol error. Clean EOF after a
  snapshot ends iteration. A nonzero exit raises `HelperError`; it is not retried.
- stdout uses upstream's newline-delimited JSON protocol. UTF-8 characters may
  span reads, and one read may contain multiple events. The stream does not use
  `--human-readable` or accept a single pretty-printed JSON event spanning lines.
- The default limit is 4 MiB per event or complete command response. Exceeding it
  raises an error and closes the helper. Slow consumers apply backpressure through
  bounded pipes instead of accumulating an unbounded Python event queue.
- stderr is continuously drained, retaining only its last 64 KiB. Nonfatal stderr
  does not stop successful operations. Inspect `events.stderr` during a stream,
  or `HelperError.stderr` / `HelperTimeoutError.stderr` on failure. Successful
  short-lived commands do not expose stderr.

## Control the current player

These methods change real playback state. Call them only when intended:

```python
await remote.play()
await remote.pause()
await remote.toggle_play_pause()
await remote.previous_track()
await remote.next_track()
await remote.seek(42.5)  # Seconds; sends 42500000 microseconds upstream
```

You can also import `Command` from the package and call
`await remote.send(Command.PLAY)`.

Arguments are validated and passed as a subprocess argument list, never through
a shell. `seek()` accepts finite, nonnegative seconds, rounded to the nearest
integer microsecond using Python's `round()`, within the upstream signed 64-bit
range. Seeking to zero is supported.

**Commands target the player selected by the system at dispatch time.** The API
does not enumerate or lock arbitrary sessions. If the current player changes
from A to B after `get()`, the next control may go to B. This version does not
provide target-player checks; even a future check would leave a race between
checking and dispatching.

Success means the upstream command exited successfully, not that the player
acknowledged or applied it. In particular, seeking has no player acknowledgement.
Upstream's implicit application-launch behavior is preserved, so some commands
may launch a player.

## Types, units, and errors

`get()` and stream events return `NowPlaying | None`. A null or empty snapshot
means no session is reported. Nonempty snapshots preserve missing and unknown
fields. `--allow-missing-title` is enabled by default, so a session can have no
title. Missing fields are not replaced with empty strings or zero.

| Attribute | Type and unit |
| --- | --- |
| `bundle_identifier`, `title`, `artist`, `album` | `str` or `None` |
| `playing` | `bool` or `None` |
| `duration`, `elapsed_time` | `float` or `None`, in seconds; elapsed time is the position at `timestamp`, not a live clock |
| `timestamp` | `float` or `None`, Unix epoch seconds |
| `playback_rate` | `float` or `None`, playback multiplier |
| `raw` | Top-level read-only mapping preserving upstream keys, nulls, and original units; unknown nested objects are not recursively frozen |

Public time attributes, `seek()`, and all timeouts use seconds. `raw` deliberately
preserves upstream microsecond fields such as `durationMicros`, `elapsedTimeMicros`,
and `timestampEpochMicros`. This version does not extrapolate playback progress.

Artwork is omitted by default. With `MediaRemote(include_artwork=True)`, `raw` may
include base64-encoded `artworkData`, depending on the player.

The complete configuration is:

```python
remote = MediaRemote(
    timeout=5.0,
    initialization_timeout=5.0,
    include_artwork=False,
    max_output_bytes=4 * 1024 * 1024,
)
```

The output limit can be set between 1 KiB and 64 MiB.

All public exceptions are available from the package root:

- `MediaRemoteError`: common runtime error base class.
- `HelperError`: helper startup or exit failure, with `returncode` and `stderr`.
- `HelperTimeoutError`: command or initialization timeout; also a `TimeoutError`.
- `ProtocolError`: invalid or oversized protocol output.
- `UnsupportedPlatformError`: attempted use on a non-macOS platform.

Invalid API arguments raise `ValueError`.

## Upstream and packaging

Package version `0.1.0a1` pins upstream
[v0.7.7](https://github.com/ungive/mediaremote-adapter/releases/tag/v0.7.7), commit
[`e3ff5021eb0875858bd05f48d2e9ba2e962d1cf6`](https://github.com/ungive/mediaremote-adapter/tree/e3ff5021eb0875858bd05f48d2e9ba2e962d1cf6).
[upstream.lock.json](https://github.com/Mai-icy/macos-mediaremote-python/blob/main/upstream.lock.json) records the archive SHA-256, deployment
target, and package-to-upstream version mapping. Each build extracts verified
archive bytes into a fresh directory. It does not build from an edited checkout
or fetch a moving `latest` version at runtime.

The build uses standard `setuptools.build_meta` with small hooks to build the
native resources and set the wheel tag. It needs no CPython extension, CMake
Python binding, or additional build backend. See the
[setuptools customization documentation](https://setuptools.pypa.io/en/latest/userguide/extension.html)
and [platform tag specification](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/).

Upstream CMake builds both arm64 and x86_64. This package produces a universal2
wheel tagged `py3-none-macosx_11_0_universal2`, with `Root-Is-Purelib: false`.
`none` means the helper is independent of the CPython ABI; the platform tag must
not be changed to `any`.

The upstream native and Perl sources are unmodified. Packaging flattens the
framework's `Versions/A` directory to avoid relying on wheel installers to
preserve symlinks, changes its dylib install name to
`@rpath/MediaRemoteAdapter.framework/MediaRemoteAdapter`, and applies and verifies
an ad-hoc signature. The upstream test client is not bundled, and the `test`
command, which may create a synthetic Now Playing entry, is not exposed or run.

## Building from source

Requires macOS, Xcode Command Line Tools, CMake, and Python 3.11.8+:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install 'setuptools>=77,<85' build pytest pytest-asyncio
.venv/bin/python -m pytest -q
.venv/bin/python -m build
```

`python -m build` creates an sdist, then builds a wheel from it. The sdist includes
this project's build scripts, lock file, licenses, tests, and examples, but not
the upstream source archive. Source installation requires native build tools and
network access to the pinned GitHub archive. Build isolation also installs the
build dependencies declared in `pyproject.toml`.

In an existing source directory, `.build/upstream/source.tar.gz` can be reused as
a SHA-256-verified cache. Building from an sdist downloads it again. These steps
only happen at build time.

## Support and limitations

- The native deployment target is macOS 11.0. This is a binary build target,
  not a runtime guarantee for every macOS 11+ release. Python's own deployment
  requirements also apply.
- Live media metadata and streaming have been verified on the development Mac,
  running macOS 26.5.1 on Apple Silicon. Hosted CI separately checks installation
  and read-only helper execution on Intel and Apple Silicon; it does not exercise
  real desktop players.
- This package depends on private MediaRemote APIs and the system Perl access
  mechanism. Future macOS updates may break it. It does not require disabling SIP,
  modifying system files, or obtaining Spotify OAuth or automation permissions.
- Browsers and other players may report different fields, omit titles or artwork,
  or ignore some commands.
- The pinned upstream `stream.m` still calls `requestAll()` before registering
  notifications. This leaves a potential initialization window for missed updates.
  The first event is not an atomic subscription-ready barrier. This package keeps
  upstream behavior without native timing patches or player-specific controls.
- `get()` returning `None` alone cannot prove private API access is working: no
  active session and an access failure may be hard to distinguish. Read-only
  verification does not create synthetic media to resolve that uncertainty.

## Validation status

Validated on 2026-09-11 with macOS 26.5.1, Apple Silicon, and Python 3.14.5:

- 88 automated tests passed, covering protocol parsing, time units, control
  arguments, timeouts, cancellation, stderr, backpressure, and process cleanup.
  Playback controls were tested using simulated helpers.
- A universal2 wheel was built from the sdist and installed offline in a new
  virtual environment outside the repository. The read example and a read-only
  subscription ran from that installation.
- Installed resources were checked for both architectures, the macOS 11.0
  deployment target, framework signature, system library dependencies, resource
  lookup, and wheel RECORD integrity.
- Live reads returned a nonempty Now Playing snapshot, the stream received
  updates, and cancellation reaped the helper. No real playback controls or
  upstream `test` command were executed.
- Interactive Intel desktops, real playback controls, a player compatibility
  matrix, Developer ID signing, and notarized distribution remain unverified.
  See the CI workflow below for automated Python and hosted macOS coverage.

`examples/verify_installed.py` performs the installed-wheel read-only audit. It
does not send playback controls or print actual track metadata values.

## License and release status

The wrapper currently uses BSD-3-Clause; see [LICENSE](https://github.com/Mai-icy/macos-mediaremote-python/blob/main/LICENSE). The license
choice will be confirmed by the project owner before a package release.
Upstream copyright belongs to Jonas van den Berg and contributors. Its original
license is preserved in [licenses/mediaremote-adapter.txt](https://github.com/Mai-icy/macos-mediaremote-python/blob/main/licenses/mediaremote-adapter.txt)
and bundled with the wheel. The wrapper is independently implemented against the
public CLI/JSON protocol.

Framework layout changes, install-name changes, and re-signing are packaging
steps performed by this project, not official upstream artifacts.

Source code and local build instructions are available. Nothing has been
published to PyPI/TestPyPI. The distribution name is `macos-mediaremote-python`;
license confirmation, the supported platform range, and the signing strategy
will be settled before a package release.

## CI and release workflow

`.github/workflows/release.yml` runs on pushes to `main`, pull requests, and
manual dispatch. Ordinary pushes and pull requests never upload to PyPI.

The workflow tests Python 3.11 through 3.14, builds a universal2 wheel from the
sdist, runs `twine check --strict`, and installs that same wheel in fresh
Apple Silicon and Intel macOS 15 environments on Python 3.11 and 3.14. Runtime
tests run outside the source checkout. The installed-wheel audit verifies
resources, signatures, deployment targets, library dependencies, and a read-only
`get()` call. A successful empty read on a hosted runner is not evidence of live
player compatibility; desktop playback and streaming still need separate tests.

`release_checks.py` rejects inconsistent package versions, upstream pins, and
architecture settings. The wheel tag is derived from the locked deployment
target. You can run the metadata checks locally without invoking the helper:

```sh
python release_checks.py
```

Publishing uses PyPI Trusted Publishing with these identifiers:

| Setting | Value |
| --- | --- |
| Project | `macos-mediaremote-python` |
| GitHub owner | `Mai-icy` |
| Repository | `macos-mediaremote-python` |
| Workflow filename | `release.yml` |
| GitHub environment | `pypi` |

For an authorized release, create a `vVERSION` tag matching the package version,
then manually dispatch this workflow at that tag with `publish=true`. The input
defaults to false. Publishing requires all checks to pass and approval in the
`pypi` environment. Only the publishing job receives OIDC permissions; it uploads
the already-tested artifacts without rebuilding. No persistent PyPI token or
TestPyPI workflow is used. Creating or pushing a tag alone does not upload a
release.
