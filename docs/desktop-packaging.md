# Desktop packaging

## Output model

A release consists of four native parts:

1. Tauri/Rust host executable;
2. embedded React/Vite assets;
3. PyInstaller `podcast-intelligence-engine` sidecar;
4. FFmpeg and FFprobe sidecars.

Tauri packages all parts into the platform's normal application bundle and
installer. Python, Node.js, PostgreSQL, Redis, MinIO, and Docker are not required
on an end user's computer.

## Why the Python engine remains

The original application already had nontrivial, tested behavior for source
resolution, SSRF-resistant downloads, FFmpeg processing, published transcript
parsing, multiple AI protocols, typed structured outputs, speaker-aware
chunking, versioned summaries, grounded citations, exports, and MCP. Rewriting
that entire domain in Rust or Go would increase regression risk without
improving the packaging boundary. Rust owns native lifecycle and security-
sensitive desktop integration; Python remains an opaque packaged engine.

## Sidecar naming

Tauri resolves external binaries by logical name and target triple. Before
`tauri build`, the staging directory contains names such as:

```text
frontend/src-tauri/binaries/
  podcast-intelligence-engine-aarch64-apple-darwin
  ffmpeg-aarch64-apple-darwin
  ffprobe-aarch64-apple-darwin
```

Windows adds `.exe`:

```text
podcast-intelligence-engine-x86_64-pc-windows-msvc.exe
```

`backend/scripts/build_engine.py` creates these names and executable modes.
Never commit generated sidecars to source control.

## FFmpeg acquisition and attribution

`scripts/fetch_media_tools.py` downloads FFmpeg/FFprobe from the pinned release:

```text
descriptinc/ffmpeg-ffprobe-static @ b6.1.2-rc.1
```

The script:

- maps the Rust target to an upstream platform asset;
- downloads only the required executables and notices;
- computes SHA-256 for every file;
- verifies the release-provided SHA-256 digest when available;
- writes `SOURCE.json` with repository, release, target, asset, and digest;
- marks Unix binaries executable.

The workflow copies source metadata and upstream notices into the Tauri
resources. The packaged FFmpeg build is a separate third-party component and
may be distributed under GPL terms. Review the copied licenses before release.

For a stricter supply-chain policy, mirror the approved assets and add immutable
hard-coded checksums to the script rather than depending on release metadata.

## macOS build

```bash
./scripts/build-desktop.sh aarch64-apple-darwin
```

Build Intel on an Intel runner:

```bash
./scripts/build-desktop.sh x86_64-apple-darwin
```

The Python engine must be built on the same architecture as the target. The
workflow intentionally emits two separate macOS artifacts instead of pretending
that a PyInstaller sidecar is universal. A universal application would require
combining compatible Rust and Python/FFmpeg binaries and validating the complete
nested signing structure.

### Signing and notarization

Unsigned bundles are suitable for local testing only. For distribution:

1. enroll in the Apple Developer Program;
2. install a Developer ID Application certificate on the runner;
3. configure Tauri's signing identity and Apple credentials/secrets;
4. ensure the engine, FFmpeg, and FFprobe nested binaries are signed;
5. notarize the final `.app`/`.dmg`;
6. staple and verify the notarization ticket.

Do not disable hardened runtime or Gatekeeper as a substitute for correct nested
code signing.

## Windows build

```powershell
.\scripts\build-desktop.ps1 -Target x86_64-pc-windows-msvc
```

The build requires the MSVC toolchain. WebView2 is used by Tauri; supported
Windows 10/11 systems generally include it, but enterprise images may need the
runtime installed.

### Code signing

Configure an Authenticode certificate in the release environment and sign the
final installer/binaries. Unsigned installers can trigger SmartScreen warnings.
Keep private keys in the CI secret store or use a managed hardware/cloud signing
service.

## GitHub Actions matrix

`.github/workflows/build-desktop.yml` runs on:

| Runner | Target |
|---|---|
| `macos-14` | `aarch64-apple-darwin` |
| `macos-15-intel` | `x86_64-apple-darwin` |
| `windows-latest` | `x86_64-pc-windows-msvc` |

Each job:

1. checks out source;
2. installs Python 3.12, Node 22, uv, and Rust target;
3. installs engine/frontend dependencies;
4. downloads media tools;
5. builds and stages the PyInstaller engine;
6. validates Python, TypeScript, tests, and Rust;
7. builds Tauri bundles;
8. uploads `release/bundle/**` as a workflow artifact.

Artifacts are retained for 14 days. Tag-triggered jobs do not automatically
publish a GitHub Release; this avoids distributing unsigned software by
accident. Add a separate release job only after signing is configured.

## Local development

A full `tauri dev` session still requires staged sidecars. One practical flow is:

```bash
# Build/stage engine and media tools for the host target
./scripts/build-desktop.sh "$(rustc -vV | sed -n 's/^host: //p')"

# Then use the normal iterative Tauri command
cd frontend
npm run tauri dev
```

The first command also creates a release bundle. For faster iteration, invoke
`fetch_media_tools.py` and `backend/scripts/build_engine.py` directly, then run
`npm run tauri dev`.

## Version synchronization

Before a release, update the same semantic version in:

- `frontend/package.json`;
- `frontend/src-tauri/Cargo.toml`;
- `frontend/src-tauri/tauri.conf.json`;
- `backend/pyproject.toml` when the engine package version changes.

The Tauri version controls installer metadata. The engine API reports the
Python package version.

## Reproducibility notes

- Python and JavaScript dependency files are present, but a new lock refresh
  could not be generated in the conversion environment because external package
  registries were unavailable.
- CI uses `uv sync` and `npm install`; refresh and commit `uv.lock` plus a new
  `package-lock.json` on a connected trusted machine before a controlled release.
- FFmpeg release tag and computed file hashes are recorded per build.
- Native installer bytes may still vary because of signing timestamps, platform
  tooling, and upstream package resolution until dependency locks are refreshed.
