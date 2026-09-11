# Repository instructions

## Start here

- Communicate with the maintainer in Chinese. Write README content, code
  comments, docstrings, and user-facing demo text in English.
- Read this file and `README.md`, then inspect `git status --short` before edits.
  Preserve existing work and keep changes within the requested scope.
- Treat `pyproject.toml`, `src/macos_mediaremote/__init__.py`,
  `upstream.lock.json`, and `.github/workflows/release.yml` as the sources of
  current version, upstream, and release configuration. Do not copy version
  numbers or test counts from historical notes without checking them.
- If present locally, `NEXT_SESSION_PROMPT.md` is historical bootstrap context,
  not a required file. Its provisional naming and pre-publication status are
  outdated. Current user instructions and authorization take precedence over
  repository notes. Do not request authorization again for actions already
  authorized in the active session.

## Product and API boundaries

- This is an independent, unofficial Python wrapper for
  `https://github.com/ungive/mediaremote-adapter`.
- Distribution: `macos-mediaremote-python`. Import: `macos_mediaremote`.
  Repository: `https://github.com/Mai-icy/macos-mediaremote-python`.
- Keep the public API small and centered on asyncio: snapshots, subscriptions,
  playback commands, typed values, errors, and deterministic cleanup.
- Keep documentation about the wrapper itself. Do not frame its purpose around
  Spotify, Qt, OAuth, lyrics applications, or unrelated dependency comparisons.
- Do not add a GUI framework, player-specific integration, synchronous API,
  plugin system, or Python runtime dependency without a task that requires it.
- Commands act on the system's current Now Playing player. Do not promise
  atomic player targeting, command acknowledgement, or identical player support.
- Public time values use seconds. Raw metadata retains upstream names and units.
  Preserve missing fields and unknown metadata; snapshot position is not a live
  progress clock. An initial empty stream event can precede player metadata.

## Code map

- `src/macos_mediaremote/client.py`: public async client and stream lifecycle.
- `src/macos_mediaremote/_process.py`: helper execution, bounded I/O, cleanup.
- `src/macos_mediaremote/models.py`: snapshots and protocol decoding.
- `src/macos_mediaremote/errors.py`: public runtime error types.
- `native_build.py`, `setup.py`, `MANIFEST.in`: native build and distribution.
- `upstream.lock.json`: verified upstream source and build configuration.
- `release_checks.py`: version, upstream pin, and release tag validation.
- `tests/`: simulated protocol/process behavior and release checks.
- `examples/verify_installed.py`: installed-wheel audit and read-only live checks.
- `demo/`: standalone PyCharm consumer of the published PyPI package. Keep its
  pinned requirement deliberate; do not silently switch it to an editable build.

## Upstream and packaging changes

- Before upgrading upstream, inspect its official release, source, CLI/JSON
  protocol, and license. Pin a full commit and verify the archive SHA-256.
- Preserve the upstream system Perl / DynaLoader host mechanism. Do not replace
  it with direct Python loading of the private framework without investigation.
- Keep upstream native sources unmodified. Explain and obtain a maintainer
  decision before introducing native patches unless already authorized.
- Installation, import, and runtime must not download native code. A compatible
  wheel bundles the framework, Perl script, lock information, and licenses.
- Preserve universal2 architecture coverage and correct macOS wheel tags.
  Native resources must never ship in an `any` wheel. Derive the deployment
  target from the lock file; a build target is not proof of runtime support.
- Preserve framework layout handling, relocatable library references, signature
  verification, and the upstream BSD-3-Clause copyright and license notices.
- Source builds require native build tools and network access. Do not claim that
  sdist installation has the same prerequisites as wheel installation.

## Runtime and validation

- Launch helpers with argument lists, never shell interpolation. Bound stdout
  and retained stderr, drain stderr, and handle fragmented UTF-8 and JSON lines.
- Keep initialization deadlines separate from ordinary stream silence. Preserve
  cancellation and close/reap helpers on normal exit, errors, and cancellation.
  Do not add unlimited automatic retries.
- Use project or temporary virtual environments; do not change global tools or
  environments belonging to another project.
- For runtime, protocol, or packaging changes, run the relevant tests and release
  checks with the project environment:

  ```sh
  .venv/bin/python release_checks.py
  .venv/bin/python -m pytest -q
  ```

- For packaging or upstream changes, build into a fresh output directory with
  `python -m build`, run `python -m twine check --strict` on those artifacts, and
  install that exact wheel into a clean environment. Run the installed audit
  from outside the source checkout. Check both architectures through CI.
- Use `examples/verify_installed.py` for resource, signature, read, stream, and
  cleanup checks. `--read-once` omits streaming; `--resources-only` omits native
  execution. A successful empty CI read does not prove desktop player behavior.
- Read-only native checks are allowed. Real playback controls and the upstream
  synthetic-media `test` need explicit authorization because they affect the
  user's player. Simulate controls in automated tests.
- Documentation-only edits need a diff check, not a native rebuild. For demo
  edits, run a short read-only check against its installed package.
- Report actual checks and remaining gaps. Do not equate a successful build,
  simulated controls, or hosted CI with full desktop compatibility.

## Git, publication, and local files

- Do not modify the adjacent `Spotify-lyrics-window` repository or inspect its
  credentials, configuration, or unrelated personal files.
- Only the root `README.md` and `AGENTS.md` may be uploaded as Markdown under
  the maintainer's current preference. Other local Markdown notes stay ignored;
  do not force-add them. Distribution archives include only `README.md` as
  Markdown, excluding these agent instructions and local session notes.
- Keep virtual environments, build output, local audit logs, and IDE settings
  out of Git. Avoid collecting actual track metadata in shared validation logs.
- When commits are requested, group coherent changes by module and use English
  emoji-style messages such as `:sparkles: Add ...` or `:bug: Fix ...`.
- Maintenance work alone does not authorize a release. When publication is
  authorized, use the existing Trusted Publishing workflow and normal `pypi`
  environment approval. Do not bypass its protections or request secret tokens
  in chat. Do not publish to TestPyPI unless requested.
- Release versions must agree in the project metadata, package version, and
  lock file. Update version-specific README examples and demo requirements as
  appropriate. Never move a published release tag or reuse a published version.
- Dispatch `release.yml` at the matching `vVERSION` tag with `publish=true` only
  for an authorized release. Ordinary pushes and tags alone do not publish.
- After publication, install the exact version from official PyPI in a clean
  environment, verify its artifact hash, and perform a read-only runtime check.

## Keep these instructions useful

Update this file when architecture, workflows, or maintainer preferences change.
Keep it focused on durable decisions and executable checks, not session history.
Agents that do not discover `AGENTS.md` automatically should be told to read it
explicitly at the start of a task. Keep this file tracked so a fresh GitHub clone
has the same maintenance instructions.
