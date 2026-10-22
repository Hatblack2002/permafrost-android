# Permafrost Android — Agent Handoff / Project Map

> **Purpose:** This is the operational handoff for any coding agent or
> human who continues the Android port. Read this file before changing
> code. It records the current verified state and the open problem, in
> one place, with traceable evidence.

**Repository:** https://github.com/Hatblack2002/permafrost-android
**Working branch:** `fix/gles-clip-varying-and-assets`
**Active PR:** https://github.com/Hatblack2002/permafrost-android/pull/5
**Upstream engine:** https://github.com/eduard-permyakov/permafrost-engine
**Pinned upstream baseline:** `083a99cace3eb047e7a3ccb7dc6b22eb78e3967f` (v1.18)
**Target device:** Samsung Galaxy S21 FE 5G (Android 13, Adreno GPU)

## Estado actual (Run #53)

Baseline: Run #53 of `android-game-apk.yml`, commit `279866f` (the
later docs-only commit `4f49869` adds no code).

Verified in CI:

- Run #53: https://github.com/Hatblack2002/permafrost-android/actions/runs/39674660107 (SUCCESS)
- 44/44 GLES 3.2 shader files pass `glslangValidator` (0 failures).
- Full-game APK generated and uploaded (artifact
  `pf-android-game-debug-apk`, artifact ID `12381013518`, ~112.5 MB):
  https://github.com/Hatblack2002/permafrost-android/actions/runs/39674660107/artifacts/12381013518
- `libmain.so` (arm64-v8a) compiles 97 C source files with CPython 2.7,
  mimalloc and OpenAL Soft, and exports `SDL_main`.

NOT verified:

- Boot on a real device.

Open problem:

- The app installs but closes immediately on launch without showing
  anything. The root cause has not been captured yet. Do not guess:
  capture the boot report first (PFActivity on-screen report, or the
  `boot-report*.txt` / `java-crash.txt` files in the app
  external-files directory), then fix only what the report
  demonstrates, one change at a time, bumping versionName/versionCode
  per build.

PR #5 (short): GLES 3.2 shader-validation fixes for all 13 previously
failing shaders (transformer + regression test), asset / script /
Python 2.7 stdlib packaging, and Android boot glue with on-screen boot
diagnostics.

Evidence rules:

- CI success = build/link evidence only. It is not proof the game
  starts. Never claim "works" without a device log.
- State the exact branch, commit SHA, workflow run and artifact for any
  APK you share. Do not substitute older artifacts.
