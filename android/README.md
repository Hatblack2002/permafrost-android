# Android native port — current engineering gate

This is a native SDL2/NDK port of the real Permafrost engine, not a web wrapper. The upstream engine is vendored under `engine/`; do not push changes to the upstream repository.

## Required order of work

1. **Android shell and SDL2:** use the SDL2 Android project template as the starting point, build ARM64 with GLES context creation, and confirm the native activity starts.
2. **Renderer portability:** replace desktop-only GLEW initialization with an Android/GLES loader strategy; gate or replace unsupported entry points instead of doing a blind header substitution.
3. **Shader portability:** classify every shader by GLSL version and feature requirements. Geometry shaders, compute shaders, SSBOs and image load/store cannot be assumed available in GLES 3.0.
4. **Native dependencies:** create an ARM64 build path for SDL2, Python 2.7 runtime, OpenAL Soft and allocator; the current engine Makefile is desktop-specific and is not an Android build recipe.
5. **Touch UX:** verify finger coordinates against SDL logical/drawable sizes; implement selection, drag/pan, pinch zoom, minimap interaction and in-game UI actions.
6. **Acceptance:** build a debug APK, preserve the APK as a workflow artifact, inspect startup logs, and test on the target phone. A CI green check alone is not device acceptance.

## Evidence rule

A source audit is not a compile. A successful desktop Linux build is not an Android build. A successful Android build is not proof the game renders or that the controls work on a phone. Report each milestone separately and do not claim an APK until the workflow actually produces one.
