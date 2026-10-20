# Permafrost Android — full-engine ARM64 compilation milestone.
#
# This script compiles the vendored engine sources as an arm64-v8a static
# library against the GLES portability layer (pf_gl.h) and the AArch64
# scheduler port. It is NOT linked into an app yet:
#   - the scripting subsystem (src/script/py_*.c) is excluded because it
#     requires an ARM64 build of the embedded Python 2.7 runtime, which is
#     a separate milestone (docs/PORT_STATUS.md),
#   - a successful compile is compile-level evidence only; it does not
#     claim the engine runs on a device (repo evidence rule).
#
# Driven by .github/workflows/android-engine-compile-report.yml with:
#   ndk-build -k NDK_PROJECT_PATH=. NDK_APPLICATION_MK=Application.mk \
#             APP_BUILD_SCRIPT=Android-engine.mk
LOCAL_PATH := $(call my-dir)

# Three levels up: this makefile lives in android/app/jni/, and the
# vendored engine is at the repository root (engine/). With only two
# levels the path resolves to android/engine, every wildcard comes back
# empty and ndk-build exits instantly, producing an empty compile report.
PF_ROOT := $(LOCAL_PATH)/../../../engine

PF_SRCS := \
    $(wildcard $(PF_ROOT)/src/*.c) \
    $(wildcard $(PF_ROOT)/src/anim/*.c) \
    $(wildcard $(PF_ROOT)/src/audio/*.c) \
    $(wildcard $(PF_ROOT)/src/game/*.c) \
    $(wildcard $(PF_ROOT)/src/lib/*.c) \
    $(wildcard $(PF_ROOT)/src/map/*.c) \
    $(wildcard $(PF_ROOT)/src/navigation/*.c) \
    $(wildcard $(PF_ROOT)/src/phys/*.c) \
    $(wildcard $(PF_ROOT)/src/render/*.c) \
    $(wildcard $(PF_ROOT)/src/script/*.c)

# The embedded Python 2.7 scripting subsystem needs an ARM64 CPython
# build before it can compile; tracked as its own port milestone.
PF_SRCS := $(filter-out $(PF_ROOT)/src/script/py_%.c,$(PF_SRCS))

# AArch64 fiber context switch (added by scripts/patch-sched-arm64.py).
PF_ASM := $(PF_ROOT)/src/context_switch.S

include $(CLEAR_VARS)

LOCAL_MODULE := pfengine

LOCAL_CFLAGS := \
    -std=c99 \
    -O2 \
    -fno-strict-aliasing \
    -fwrapv \
    -D_DEFAULT_SOURCE \
    -D_GNU_SOURCE \
    -DNDEBUG \
    -Wno-int-conversion \
    -Wno-implicit-function-declaration \
    -Wno-format

LOCAL_C_INCLUDES := \
    $(PF_ROOT)/src \
    $(PF_ROOT)/deps/SDL2/include \
    $(PF_ROOT)/deps/openal-soft/include \
    $(PF_ROOT)/deps/mimalloc/include \
    $(PF_ROOT)/deps/GLEW/include \
    $(PF_ROOT)/deps/Python/Include

LOCAL_SRC_FILES := $(PF_SRCS:$(LOCAL_PATH)/%=%) $(PF_ASM:$(LOCAL_PATH)/%=%)

include $(BUILD_STATIC_LIBRARY)
