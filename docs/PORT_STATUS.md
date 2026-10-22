# Port status

Repository: https://github.com/Hatblack2002/permafrost-android
Working branch: `fix/gles-clip-varying-and-assets` — PR #5 (open)
Upstream engine: https://github.com/eduard-permyakov/permafrost-engine
Pinned upstream baseline: `083a99cace3eb047e7a3ccb7dc6b22eb78e3967f` (v1.18)
Target device: Samsung Galaxy S21 FE 5G (Android 13, Adreno GPU)

## Estado actual (Run #53)

Baseline: Run #53 of `android-game-apk.yml`, commit `279866f` (the later
docs-only commit `4f49869` adds no code).

Verified in CI:

- 44/44 GLES 3.2 shader files pass `glslangValidator` (0 failures).
- Full-game APK generated and uploaded (artifact
  `pf-android-game-debug-apk`, artifact ID `12381013518`, ~112.5 MB).
- `libmain.so` (arm64-v8a) exports `SDL_main`.

NOT verified:

- Boot on a real device.

Open problem:

- The app installs but closes immediately on launch without showing
  anything. The root cause has not been captured yet; the on-screen
  boot report (PFActivity) is the tool to capture it.

PR #5 (short): GLES 3.2 shader-validation fixes for all 13 previously
failing shaders (transformer + regression test), asset / script /
Python 2.7 stdlib packaging, and Android boot glue with on-screen boot
diagnostics.

Next step: install the Run #53 APK on the target device, reproduce the
close, and collect the boot report shown by PFActivity (or the
`boot-report*.txt` files in the app external-files directory). Fix only
what the report demonstrates, one change at a time, bumping
versionName/versionCode per build.
