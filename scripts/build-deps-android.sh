#!/usr/bin/env bash
#
# build-deps-android.sh — cross-builds the three boot-blocking engine
# dependencies for Android arm64-v8a:
#
#   1. CPython 2.7.17  (embedded interpreter required by src/script/py_*.c;
#                       engine boots strictly via S_Init)
#   2. mimalloc 2.x    (the engine's allocator backend; hard link dep)
#   3. OpenAL Soft 1.21.1 (OpenSL ES backend; Audio_Init is fatal-fail)
#
# Everything is built inside this CI job (no system-wide installs) and
# staged under $STAGE as:
#
#   prebuilt/python/libpython2.7.a   + prebuilt/python/pyconfig.h
#   prebuilt/mimalloc/libmimalloc.a
#   prebuilt/openal/libopenal.a
#
# Only the static library of CPython is produced (the engine embeds the
# interpreter; it never needs an on-device python binary), matching the
# upstream desktop build which uses --without-threads (script tasks run
# as scheduler fibers on the main thread).
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NDK="${ANDROID_NDK_LATEST_HOME:-${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}}"
if [ -z "$NDK" ]; then
    echo "error: no Android NDK found (set ANDROID_NDK_LATEST_HOME)" >&2
    exit 1
fi
echo "NDK: $NDK"

API=24
ABI=arm64-v8a
HOST_TRIPLE=aarch64-linux-android
BUILD_TRIPLE=x86_64-pc-linux-gnu
WORK="${PF_DEPS_WORK:-/tmp/pf-deps-build}"
STAGE="${1:-$WORK/stage}"
JOBS="$(nproc)"

TC="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin"
CROSS_CC="$TC/$HOST_TRIPLE$API-clang"
CROSS_AR="$TC/llvm-ar"
CROSS_RANLIB="$TC/llvm-ranlib"
CROSS_READELF="$TC/llvm-readelf"
CROSS_NM="$TC/llvm-nm"

for tool in "$CROSS_CC" "$CROSS_AR" cmake; do
    [ -x "$tool" ] || command -v "$tool" >/dev/null || {
        echo "error: required tool missing: $tool" >&2; exit 1; }
done

rm -rf "$WORK"
mkdir -p "$WORK/hostbin" "$STAGE/prebuilt/python" "$STAGE/prebuilt/mimalloc" "$STAGE/prebuilt/openal"
STAGE="$(cd "$STAGE" && pwd)"

echo "=== [1/3] CPython 2.7: host build (pgen + PYTHON_FOR_BUILD) ==="
cp -r "$REPO_ROOT/engine/deps/Python" "$WORK/py-host"
(
    cd "$WORK/py-host"
    ./configure --prefix="$WORK/py-host-install" --without-threads \
        > host-configure.log 2>&1 || { tail -n 80 host-configure.log; exit 1; }
    make -j"$JOBS" python Parser/pgen \
        > host-make.log 2>&1 || { tail -n 80 host-make.log; exit 1; }
    # -S: skip site.py — a bare `make python` build has no C extension
    # modules (errno/os live in setup.py-built .so files) and site would
    # fail on the import chain. The host interpreter is only used for
    # pgen/autotools chores, never to run the game.
    ./python -S -c 'import sys; assert sys.version_info[:2] == (2, 7), sys.version; print("host python OK:", sys.version)'
)
cp "$WORK/py-host/python" "$WORK/hostbin/python"
cp "$WORK/py-host/Parser/pgen" "$WORK/hostbin/pgen"

echo "=== [2/3] CPython 2.7: arm64 cross build (libpython2.7.a) ==="
cp -r "$REPO_ROOT/engine/deps/Python" "$WORK/py-arm"
(
    cd "$WORK/py-arm"
    export CC="$CROSS_CC" AR="$CROSS_AR" RANLIB="$CROSS_RANLIB" READELF="$CROSS_READELF"
    ./configure \
        --host="$HOST_TRIPLE" --build="$BUILD_TRIPLE" \
        --prefix="$WORK/py-arm-install" \
        --without-threads --without-signal-module --disable-ipv6 \
        ac_cv_file__dev_ptmx=yes ac_cv_file__dev_ptc=no \
        PYTHON_FOR_BUILD="$WORK/hostbin/python -E" \
        > cross-configure.log 2>&1 || { tail -n 120 cross-configure.log; exit 1; }

    # CPython 2.7 builds its C extension modules through setup.py as .so
    # files by default — impossible here (no on-device interpreter, no
    # dynamic loading in the embedded lib). Enforce a static set instead:
    # makesetup folds these into libpython2.7.a and registers them in
    # _PyImport_Inittab. The set covers every import-time C dependency of
    # the engine's game scripts (math, itertools, operator, _collections,
    # _heapq, _bisect, cStringIO, errno, time) plus common extras; the
    # rest of the game runtime comes from the engine's pure-Python
    # scripts/stdlib.
    cat > Modules/Setup.local <<'SETUP'
# Static modules for the embedded Android interpreter (scripts/build-deps-android.sh)
errno errnomodule.c
posix posixmodule.c
time timemodule.c
math mathmodule.c
operator operator.c
itertools itertoolsmodule.c
_collections _collectionsmodule.c
_heapq _heapqmodule.c
_bisect _bisectmodule.c
array arraymodule.c
binascii binascii.c
_struct _struct.c
strop stropmodule.c
cStringIO cStringIO.c
cPickle cPickle.c
_random _randommodule.c
_functools _functoolsmodule.c
SETUP

    make -j"$JOBS" libpython2.7.a PGEN="$WORK/hostbin/pgen" \
        > cross-make.log 2>&1 || { tail -n 120 cross-make.log; exit 1; }
)
CROSS_LIB="$WORK/py-arm/libpython2.7.a"
[ -f "$CROSS_LIB" ] || { echo "error: libpython2.7.a not produced" >&2; exit 1; }
# Guard: the statically-enabled module set must have made it into the
# archive's builtin-module table (initmath/initerrno/...), and the
# library must really be AArch64 (not a stale/host-arch artifact).
"$CROSS_READELF" -h "$CROSS_LIB" | grep -q "AArch64" || {
    echo "error: libpython2.7.a is not AArch64" >&2; exit 1; }
for sym in initmath initerrno initposix inittime inititertools initoperator; do
    "$CROSS_NM" "$CROSS_LIB" 2>/dev/null | grep -q "T $sym" || {
        echo "error: builtin module missing from libpython2.7.a: $sym" >&2
        exit 1;
    }
done
"$CROSS_NM" "$CROSS_LIB" | grep -c " T init" | xargs echo "builtin module init functions:"
cp "$CROSS_LIB" "$STAGE/prebuilt/python/libpython2.7.a"
cp "$WORK/py-arm/pyconfig.h" "$STAGE/prebuilt/python/pyconfig.h"

echo "=== [3/3] mimalloc + OpenAL Soft (CMake, arm64) ==="
TCFILE="$NDK/build/cmake/android.toolchain.cmake"

cmake -S "$REPO_ROOT/engine/deps/mimalloc" -B "$WORK/mi" \
    -DCMAKE_TOOLCHAIN_FILE="$TCFILE" \
    -DANDROID_ABI="$ABI" -DANDROID_PLATFORM="android-$API" \
    -DCMAKE_BUILD_TYPE=Release \
    -DMI_BUILD_SHARED=OFF -DMI_BUILD_OBJECT=OFF -DMI_BUILD_TESTS=OFF \
    > "$WORK/mi-cmake.log" 2>&1 || { tail -n 80 "$WORK/mi-cmake.log"; exit 1; }
cmake --build "$WORK/mi" -j"$JOBS" > "$WORK/mi-build.log" 2>&1 \
    || { tail -n 80 "$WORK/mi-build.log"; exit 1; }
MI_LIB="$(find "$WORK/mi" -name 'libmimalloc.a' | head -n1)"
[ -n "$MI_LIB" ] || { echo "error: libmimalloc.a not produced" >&2; exit 1; }
cp "$MI_LIB" "$STAGE/prebuilt/mimalloc/libmimalloc.a"

cmake -S "$REPO_ROOT/engine/deps/openal-soft" -B "$WORK/oal" \
    -DCMAKE_TOOLCHAIN_FILE="$TCFILE" \
    -DANDROID_ABI="$ABI" -DANDROID_PLATFORM="android-$API" \
    -DCMAKE_BUILD_TYPE=Release \
    -DLIBTYPE=STATIC \
    -DALSOFT_UTILS=OFF -DALSOFT_EXAMPLES=OFF -DALSOFT_TESTS=OFF \
    -DALSOFT_BACKEND_OPENSL=ON \
    > "$WORK/oal-cmake.log" 2>&1 || { tail -n 80 "$WORK/oal-cmake.log"; exit 1; }
cmake --build "$WORK/oal" -j"$JOBS" > "$WORK/oal-build.log" 2>&1 \
    || { tail -n 80 "$WORK/oal-build.log"; exit 1; }
OAL_LIB="$(find "$WORK/oal" -name 'libopenal.a' | head -n1)"
[ -n "$OAL_LIB" ] || { echo "error: libopenal.a not produced" >&2; exit 1; }
cp "$OAL_LIB" "$STAGE/prebuilt/openal/libopenal.a"
# Keep the CMake-generated OpenAL config header: al_audio.c's al.h pulls
# it in via the build's AL/ headers on some configurations.
mkdir -p "$STAGE/prebuilt/openal/AL"
cp "$WORK/oal/include/AL/al.h" "$STAGE/prebuilt/openal/AL/" 2>/dev/null || true

echo "=== staged artifacts ==="
ls -la "$STAGE/prebuilt/python" "$STAGE/prebuilt/mimalloc" "$STAGE/prebuilt/openal"
{
    echo "NDK: $NDK"
    echo "ABI: $ABI  API: $API"
    echo "python: $(file "$STAGE/prebuilt/python/libpython2.7.a")"
    echo "built: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$STAGE/prebuilt/BUILD_INFO.txt"

echo "OK: dependencies staged at $STAGE"
