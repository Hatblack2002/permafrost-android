# Permafrost Android shell — milestone 1 (Stage 2, step 1 of
# android/README.md): SDL2 Android shell with a real GLES 3.2 context.
#
# This build does NOT compile the engine yet; it produces the "shell
# smoke" APK that proves the Android activity, SDL2 and the GLES pipeline
# work on ARM64. The engine compilation milestone is driven by
# Android-engine.mk (see .github/workflows/android-engine-compile-report.yml).
#
# Per the repo evidence rule: this APK must be described as a shell, not
# as the ported engine.
LOCAL_PATH := $(call my-dir)

PF_ENGINE_DIR := $(LOCAL_PATH)/../../../engine
SDL_PATH := $(PF_ENGINE_DIR)/deps/SDL2

include $(CLEAR_VARS)

LOCAL_MODULE := main

LOCAL_C_INCLUDES := $(SDL_PATH)/include

LOCAL_CFLAGS := -std=c99 -O2 -Wall

LOCAL_SRC_FILES := src/pf_android_shell.c

LOCAL_SHARED_LIBRARIES := SDL2

LOCAL_LDLIBS := -lGLESv3 -lEGL -llog -landroid

include $(BUILD_SHARED_LIBRARY)

# Build the vendored SDL2 shared library itself.
include $(SDL_PATH)/Android.mk
