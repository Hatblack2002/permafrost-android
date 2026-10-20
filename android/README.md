# Android native port bootstrap

This directory is reserved for the Android application/NDK integration. It must host the original engine through SDL2's Android activity integration and a GLES-capable renderer path, not a web wrapper or a screenshot.

The first runnable milestone is a debug ARM64 APK that starts SDL, creates the correct Android graphics context, and renders an actual Permafrost map. No APK is claimed until the build and device test exist.

Required decisions before the first native build:
- SDL2 Android backend and Gradle/NDK integration.
- GLES version and renderer/shader compatibility plan.
- Android-compatible replacement/configuration for GLEW.
- Python runtime strategy for the engine's Python 2.7 scripting.
- Asset location and Android scoped-storage handling.
