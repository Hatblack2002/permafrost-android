# Permafrost Android

Android ARM64 porting workspace for [Permafrost Engine](https://github.com/eduard-permyakov/permafrost-engine).

## Important status

This repository is the Android port workspace. The upstream engine is **not modified** by this project. Android-specific changes belong here and must be isolated from upstream code as patches/adapters wherever practical.

**Current milestone: source and platform audit.** No Android APK or working port is claimed yet.

## Target device

- Android 13+
- ARM64-v8a
- Initial validation target: Samsung Galaxy S20 FE

## Porting principles

1. Preserve upstream source and license notices.
2. Keep Android changes separate from the upstream engine.
3. Do not add fake controls or UI that cannot issue real game commands.
4. Touch input must be integrated into the actual selection, camera, minimap, and command paths.
5. Verify every milestone with a build or an explicit test; do not call a screen-only mockup a port.
6. Keep game assets separate; do not redistribute assets unless their license allows it.

## Upstream

- Repository: https://github.com/eduard-permyakov/permafrost-engine
- Engine: C, OpenGL 3.3, SDL2, GLEW, embedded Python 2.7, OpenAL Soft, mimalloc.
- License: GPLv3 with a special linking exception; review upstream license text before distributing binaries or derivative work.

## Initial technical blockers

- Desktop OpenGL 3.3 / GLEW assumptions need an Android graphics compatibility audit; Android typically exposes OpenGL ES.
- Build scripts currently define Linux and Windows targets, not Android ARM64.
- Mouse-driven selection, camera, minimap, and raycast paths need touch/pointer integration.
- Python 2.7 and all native dependencies need an Android-compatible build and runtime strategy.

See [docs/ANDROID_PORT_PLAN.md](docs/ANDROID_PORT_PLAN.md).
