# Permafrost Android — full-game APK build (link milestone).
#
# Modules:
#   pfengine  (static)  : the entire vendored engine INCLUDING the Python
#                         scripting subsystem (src/script/py_*.c), EXCLUDING
#                         src/main.c (its entry point is compiled inside
#                         src/pf_android_main.c, which needs access to the
#                         static engine_init()/engine_shutdown()).
#   python2.7 (prebuilt): cross-built CPython 2.7 libpython2.7.a from the
#                         android-deps-arm64 CI workflow. The workflow stages
#                         it at jni/prebuilt/ before invoking gradle.
#   mimalloc  (prebuilt): engine allocator backend (hard dependency of
#                         src/mem.c).
#   openal    (prebuilt): OpenAL Soft with the OpenSL ES backend (hard
#                         dependency of src/audio/al_audio.c Audio_Init).
#   SDL2      (shared)  : vendored SDL 2.30, built from its own Android.mk.
#   main      (shared)  : pf_android_main.c glue (asset extraction + argv
#                         synthesis + engine boot), links everything above.
#
# The compile-only milestone remains driven by Android-engine.mk via
# .github/workflows/android-engine-compile-report.yml; this file is the
# shipping configuration.
LOCAL_PATH := $(call my-dir)

PF_ROOT      := $(LOCAL_PATH)/../../../engine
SDL_PATH     := $(PF_ROOT)/deps/SDL2
PREBUILT     := $(LOCAL_PATH)/prebuilt

ifneq ($(wildcard $(PREBUILT)/python/libpython2.7.a),)
else
$(error prebuilt dependencies missing: run scripts/build-deps-android.sh \
  (android-deps-arm64 workflow) and stage them at android/app/jni/prebuilt/)
endif

# ---------------------------------------------------------------------------
# Prebuilt dependencies
# ---------------------------------------------------------------------------
include $(CLEAR_VARS)
LOCAL_MODULE := python27
LOCAL_SRC_FILES := prebuilt/python/libpython2.7.a
LOCAL_EXPORT_C_INCLUDES := $(PF_ROOT)/deps/Python/Include $(PREBUILT)/python
include $(PREBUILT_STATIC_LIBRARY)

include $(CLEAR_VARS)
LOCAL_MODULE := mimalloc
LOCAL_SRC_FILES := prebuilt/mimalloc/libmimalloc.a
LOCAL_EXPORT_C_INCLUDES := $(PF_ROOT)/deps/mimalloc/include
include $(PREBUILT_STATIC_LIBRARY)

include $(CLEAR_VARS)
LOCAL_MODULE := openal
LOCAL_SRC_FILES := prebuilt/openal/libopenal.a
LOCAL_EXPORT_C_INCLUDES := $(PF_ROOT)/deps/openal-soft/include
include $(PREBUILT_STATIC_LIBRARY)

# ---------------------------------------------------------------------------
# Engine static library (full, minus the entry point TU)
# ---------------------------------------------------------------------------
PF_ENGINE_SRCS := \
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

# The scripting subsystem is IN for the game build (only the compile-report
# milestone excludes it, pending the ARM64 libpython build).
PF_ENGINE_SRCS := $(filter-out $(PF_ROOT)/src/main.c,$(PF_ENGINE_SRCS))

PF_ENGINE_ASM := $(PF_ROOT)/src/context_switch.S

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
    $(PF_ROOT)/deps/Python/Include \
    $(PREBUILT)/python \
    $(LOCAL_PATH)/../../../android/include

LOCAL_SRC_FILES := $(PF_ENGINE_SRCS:$(LOCAL_PATH)/%=%) $(PF_ENGINE_ASM:$(LOCAL_PATH)/%=%)

# Android port adapter layer: GLES portability header plus the runtime
# glBufferStorage / extension-flag resolution it declares.
LOCAL_SRC_FILES += ../../../android/port-src/pf_gl_android.c

# Static dependencies of the engine's own translation units: py_*.c pulls
# the embedded CPython, mem.c/perf.c/sched.c pull mimalloc, and
# audio/al_audio.c pulls OpenAL Soft.
LOCAL_STATIC_LIBRARIES := python27 mimalloc openal

include $(BUILD_STATIC_LIBRARY)

# ---------------------------------------------------------------------------
# Application glue (SDL activity entry point)
# ---------------------------------------------------------------------------
include $(CLEAR_VARS)

LOCAL_MODULE := main

# -std=c99 must be C-only (LOCAL_CONLYFLAGS): the module also compiles
# pf_stdcpp_anchor.cpp, and clang rejects -std=c99 for C++ inputs.
LOCAL_CONLYFLAGS := -std=c99
LOCAL_CFLAGS := -O2 -Wno-format

LOCAL_C_INCLUDES := \
    $(SDL_PATH)/include \
    $(PF_ROOT)/src \
    $(PF_ROOT)/deps/Python/Include \
    $(PREBUILT)/python \
    $(LOCAL_PATH)/../../../android/include

LOCAL_SRC_FILES := src/pf_android_main.c \
    src/pf_stdcpp_anchor.cpp

LOCAL_STATIC_LIBRARIES := pfengine python27 mimalloc openal

# pf_android_main.c is C, but pfengine's static deps (mimalloc, OpenAL
# Soft) are C++ and need the libc++ runtime at the final link. ndk-build
# only links the STL into modules with C++ sources unless this is set
# (NDK docs: PREBUILT static libraries section).
LOCAL_CPP_FEATURES := rtti exceptions

LOCAL_SHARED_LIBRARIES := SDL2

LOCAL_LDLIBS := -lGLESv3 -lEGL -lOpenSLES -llog -landroid -lm -ldl -lz

include $(BUILD_SHARED_LIBRARY)

# Build the vendored SDL2 shared library itself.
include $(SDL_PATH)/Android.mk
