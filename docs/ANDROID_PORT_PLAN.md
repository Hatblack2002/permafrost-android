# Android port plan

## Rule zero: preserve upstream

Do not edit the original upstream repository. Keep the upstream revision identifiable and store Android-only code and patches in this repository. Once source import is available, record the exact upstream commit SHA before applying changes.

## Stage 0 — source baseline and license

- [ ] Import a clean snapshot of upstream source without Android changes.
- [ ] Record upstream URL, commit SHA, and license notices.
- [ ] Inventory third-party licenses and assets separately.
- [ ] Ensure a reproducible upstream baseline is preserved.

## Stage 1 — dependency and graphics feasibility

- [ ] Inspect the SDL2 version and Android backend/build support.
- [ ] Determine whether GLEW can be replaced or isolated for GLES; do not assume desktop OpenGL entry points work on Android.
- [ ] Audit shader versions and unsupported extensions.
- [ ] Build ARM64 variants of SDL2, OpenAL Soft, mimalloc, and a viable Python runtime.
- [ ] Identify POSIX APIs, thread assumptions, dynamic-library paths, and filesystem assumptions that need changes.
- [ ] Produce a dependency/build report before attempting the full application.

## Stage 2 — Android shell and first renderer proof

- [ ] Add an Android Gradle application module and NDK/CMake build.
- [ ] Launch the native engine through SDL's Android activity integration (or a minimal JNI bridge if needed).
- [ ] Show the real engine loading screen and then render the existing map/scene.
- [ ] Handle Android activity pause/resume, context loss, orientation, and app backgrounding.
- [ ] Do not replace the real map with a placeholder image.

Acceptance: a debug APK launches on ARM64 and renders a real engine scene without crashing after background/foreground.

## Stage 3 — genuine touch controls

Touch actions must call the existing game systems; no decorative/inert buttons.

- Single tap: select unit/object or interact with UI.
- Drag on terrain: box selection, with clear gesture arbitration against camera movement.
- Tap destination after selection: issue movement/order through the real command path.
- Two-finger pinch: camera zoom.
- One-finger drag on empty terrain: camera pan, with an explicit mode/gesture policy that does not conflict with box selection.
- Minimap tap/drag: move camera to the selected world position.
- Touch-friendly production/build panels: dispatch the same real commands as desktop UI.
- Long press/context action: replace right-click interactions where appropriate.
- Respect safe areas, landscape orientation, screen density, and small-screen layout.

Acceptance: every visible action is wired to a real engine action; no desktop-only right-click is required to play the core loop.

## Stage 4 — performance and usability

- [ ] Profile CPU/GPU/memory on the target phone.
- [ ] Add scalable graphics settings and frame pacing.
- [ ] Test long sessions, save/load, audio focus, pause/resume, and rotation.
- [ ] Verify thermal behavior and memory pressure.

## Stage 5 — release readiness

- [ ] CI build for Android ARM64.
- [ ] License and notices audit.
- [ ] Clear instructions for obtaining legally distributable game data.
- [ ] Install and gameplay tests on a physical device.
- [ ] Publish APK only after these checks pass.

## Known upstream dependencies to audit

The upstream Makefile currently includes SDL2, GLEW, Python 2.7, OpenAL Soft, and mimalloc. Its documented build targets are Linux and Windows. The engine uses SDL mouse-state APIs in camera, selection, minimap, and raycast code. These are audit findings, not proof that the engine is already Android-compatible.
